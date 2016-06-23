#
# Copyright (c) 2013 Shotgun Software, Inc
# ----------------------------------------------------
#
import os
import sys
import unicodedata
import tank

from Katana import QtGui, QtCore


class MenuGenerator(object):
    """
    A Katana specific menu generator.
    """

    def __init__(self, engine, menu_name):
        """
        Initializes a new menu generator.

        :param engine: The currently-running engine.
        :type engine: :class:`tank.platform.Engine`
        :param menu_name: The name of the menu to be created.
        """
        self._engine = engine
        self._menu_name = menu_name
        self.root_menu = None

    @property
    def engine(self):
        """The currently-running engine."""
        return self._engine

    @property
    def menu_name(self):
        """The name of the menu to be generated."""
        return self._menu_name

    def create_menu(self):
        """
        Create the Shotgun Menu.
        """
        # Get the shotgun menu
        self.root_menu = self.get_or_create_root_menu(self.menu_name)

        # 'surfacing, Assets chair' menu
        menu_handle = self.root_menu

        # now add the context item on top of the main menu
        self._context_menu = self._add_context_menu(menu_handle)
        menu_handle.addSeparator()

        # now enumerate all items and create menu objects for them
        menu_items = []
        for (cmd_name, cmd_details) in self.engine.commands.items():
             menu_items.append(AppCommand(self.engine, cmd_name, cmd_details))

        # sort list of commands in name order
        menu_items.sort(key=lambda x: x.name)

        # now add favourites
        for fav in self.engine.get_setting("menu_favourites"):
            app_instance_name = fav["app_instance"]
            menu_name = fav["name"]

            # scan through all menu items
            for cmd in menu_items:
                 if cmd.get_app_instance_name == app_instance_name and cmd.name == menu_name:
                     # found our match!
                     cmd.add_command_to_menu(menu_handle)
                     # mark as a favourite item
                     cmd.favourite = True

        menu_handle.addSeparator()

        # now go through all of the menu items.
        # separate them out into various sections
        commands_by_app = {}

        for cmd in menu_items:
            if cmd.type == "context_menu":
                # context menu!
                cmd.add_command_to_menu(self._context_menu)

            else:
                # normal menu
                app_name = cmd.app_name
                if app_name is None:
                    # un-parented app
                    app_name = "Other Items"
                if not app_name in commands_by_app:
                    commands_by_app[app_name] = []
                commands_by_app[app_name].append(cmd)

        # now add all apps to main menu
        self._add_app_menu(commands_by_app, menu_handle)

    @classmethod
    def get_or_create_root_menu(cls, menu_name):
        """
        Attempts to find an existing menu of the specified title. If it can't be
        found, it creates one.
        """
        # Get the "main menu" (the bar of menus)
        main_menu = cls.__get_katana_main_menu()
        if not main_menu:
            return

        # Attempt to find existing menu
        for menu in main_menu.children():
            if type(menu).__name__ == "QMenu" and menu.title() == menu_name:
                return menu

        # Otherwise, create a new menu
        menu = QtGui.QMenu(menu_name, main_menu)
        main_menu.addMenu(menu)
        return menu

    @classmethod
    def __get_katana_main_menu(cls):
        layoutsMenus = [x for x in QtGui.qApp.topLevelWidgets() if type(x).__name__ == 'LayoutsMenu']
        if len(layoutsMenus) != 1:
            return

        mainMenu = layoutsMenus[0].parent()
        return mainMenu

    def destroy_menu(self):
        """
        Destroys the Shotgun menu.
        """
        if self.root_menu is not None:
            self.root_menu.clear()

    ##########################################################################################
    # context menu and UI

    def _add_context_menu(self, menu_handle):
        """
        Adds a context menu which displays the current context.
        """
        ctx = self.engine.context
        ctx_name = str(ctx)

        # create the menu object
        ctx_menu = menu_handle.addMenu(ctx_name)

        action = QtGui.QAction('Jump to Shotgun', self.root_menu, triggered=self._jump_to_sg)
        ctx_menu.addAction(action)

        action = QtGui.QAction('Jump to File System', self.root_menu, triggered=self._jump_to_fs)
        ctx_menu.addAction(action)

        ctx_menu.addSeparator()

        return ctx_menu

    def _jump_to_sg(self):
        """
        Jump to Shotgun, launch web browser.
        """
        url = self.engine.context.shotgun_url
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _jump_to_fs(self):
        """
        Jump from context to FS.
        """
        # launch one window for each location on disk
        paths = self.engine.context.filesystem_locations
        for disk_location in paths:

            # get the setting
            system = sys.platform

            # run the app
            if system == "linux2":
                cmd = 'xdg-open "%s"' % disk_location
            elif system == "darwin":
                cmd = 'open "%s"' % disk_location
            elif system == "win32":
                cmd = 'cmd.exe /C start "Folder" "%s"' % disk_location
            else:
                raise Exception("Platform '%s' is not supported." % system)

            exit_code = os.system(cmd)
            if exit_code != 0:
                self.engine.log_error("Failed to launch '%s'!" % cmd)

    ##########################################################################################
    # app menus

    def _add_app_menu(self, commands_by_app, menu_handle):
        """
        Add all apps to the main menu, process them one by one.
        """
        for app_name in sorted(commands_by_app.keys()):

            if len(commands_by_app[app_name]) > 1:
                # more than one menu entry fort his app
                # make a sub menu and put all items in the sub menu
                app_menu = menu_handle.addMenu(app_name)

                # get the list of menu cmds for this app
                cmds = commands_by_app[app_name]
                # make sure it is in alphabetical order
                cmds.sort(key=lambda x: x.name)

                for cmd in cmds:
                    cmd.add_command_to_menu(app_menu)

            else:
                # this app only has a single entry.
                # display that on the menu
                # todo: Should this be labelled with the name of the app
                # or the name of the menu item? Not sure.
                cmd_obj = commands_by_app[app_name][0]
                if not cmd_obj.favourite:
                    # skip favourites since they are alreay on the menu
                    cmd_obj.add_command_to_menu(menu_handle)


class AppCommand(object):
    """
    Wraps around a single command that you get from engine.commands
    """

    def __init__(self, engine, name, command_dict):

        self._name = name
        self._engine = engine
        self._properties = command_dict["properties"]
        self._callback = command_dict["callback"]
        self._favourite = False
        self._app = self._properties.get("app")
        self._type = self._properties.get("type", "default")
        try:
            self._app_name = self._app.display_name
        except AttributeError:
            self._app_name = None
        self._app_instance_name = None
        if self._app:
            for (app_instance_name, app_instance_obj) in engine.apps.items():
                if self._app and self._app == app_instance_obj:
                    self._app_instance_name = app_instance_name        

    @property
    def app(self):
        """The command's parent app."""
        return self._app

    @property
    def app_instance_name(self):
        """The instance name of the parent app."""
        return self._app_instance_name

    @property
    def app_name(self):
        """The name of the parent app."""
        return self._app_name

    @property
    def name(self):
        """The name of the command."""
        return self._name

    @name.setter
    def name(self, name):
        self._name = str(name)

    @property
    def engine(self):
        """The currently-running engine."""
        return self._engine

    @property
    def properties(self):
        """The command's properties dictionary."""
        return self._properties

    @property
    def callback(self):
        """The callback function associated with the command."""
        return self._callback

    @property
    def favourite(self):
        """Whether the command is a favourite."""
        return self._favourite

    @favourite.setter
    def favourite(self, state):
        self._favourite = bool(state)

    @property
    def type(self):
        """The command's type as a string."""
        return self._type

    def get_documentation_url_str(self):
        """
        Returns the documentation URL.
        """
        if self.app:
            doc_url = self.app.documentation_url
            # Deal with nuke's inability to handle unicode.
            if doc_url.__class__ == unicode:
                doc_url = unicodedata.normalize("NFKD", doc_url).encode("ascii", "ignore")
            return doc_url
        return None

    def _non_pane_menu_callback_wrapper(self, callback):
        """
        Callback for all non-pane menu commands.

        :param callback:    A callable object that is triggered
                            when the wrapper is invoked.
        """
        # This is a wrapped menu callback for whenever an item is clicked
        # in a menu which isn't the standard nuke pane menu. This ie because 
        # the standard pane menu in nuke provides nuke with an implicit state
        # so that nuke knows where to put the panel when it is created.
        # If the command is called from a non-pane menu however, this implicity
        # state does not exist and needs to be explicity defined.
        #
        # For this purpose, we set a global flag to hint to the panelling 
        # logic to run its special window logic in this case.
        #
        # Note that because of nuke not using the import_module()
        # system, it's hard to obtain a reference to the engine object
        # right here - this is why we set a flag on the main tank
        # object like this.
        setattr(tank, "_callback_from_non_pane_menu", True)
        try:
            callback()
        finally:    
            delattr(tank, "_callback_from_non_pane_menu")

    def add_command_to_menu(self, menu, enabled=True, icon=None):
        """
        Adds a command to the menu.
        
        :param menu:    The menu object to add the new item to.
        :param enabled: Whether the command will be enabled after it
                        is added to the menu. Defaults to True.
        :param icon:    The path to an image file to use as the icon
                        for the menu command.
        """
        icon = icon or self.properties.get("icon")
        new_icon=None
        if icon:
            new_icon=QtGui.QIcon(icon)
        hotkey = self.properties.get("hotkey")
        
        # Now wrap the command callback in a wrapper (see above)
        # which sets a global state variable. This is detected
        # by the show_panel so that it can correctly establish 
        # the flow for when a pane menu is clicked and you want
        # the potential new panel to open in that window.
        cb = lambda: self._non_pane_menu_callback_wrapper(self.callback)
        if hotkey:
            action = QtGui.QAction(self.name, menu,triggered=cb, icon=icon)
            #menu.addCommand(self.name, cb, hotkey, icon=icon)
        else:
            action = QtGui.QAction(self.name, menu,triggered=cb, icon=icon)
            #menu.addCommand(self.name, cb, icon=icon)

        menu.addAction(action)

