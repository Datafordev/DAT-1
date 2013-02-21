import warnings

from dat import DATRecipe, PipelineInformation
from dat.global_data import GlobalManager
from dat.vistrails_interface import Variable

from vistrails.core.application import get_vistrails_application
from vistrails.core.system import vistrails_default_file_type
from vistrails.packages.spreadsheet.spreadsheet_controller import \
    spreadsheetController
from vistrails.packages.spreadsheet.spreadsheet_tab import \
    StandardWidgetSheetTab


class VistrailData(object):
    """Keeps a list of DAT objects that are local to a vistrail file.

    This object allows components throughout the application to access the
    variables for a given vistrail, and emits notifications when the list of
    variable changes.

    It also keeps a mapping between pipeline versions and DATRecipe and writes
    it in the vistrail as annotations.

    An object of this class gets created for each currently opened vistrail
    file.
    """

    # Annotation format is:
    #   <actionAnnotation
    #           actionId="PIPELINEVERSION"
    #           key="dat-recipe"
    #           value="PlotName;param1=varname1;param3=varname2" />
    #   <actionAnnotation
    #           actionId="PIPELINEVERSION"
    #           key="dat-ports"
    #           value="param1=ID1:PORT1,ID2:PORT2;param2=ID2:PORT2" />
    #   <actionAnnotation
    #           actionId="PIPELINEVERSION"
    #           key="dat-vars"
    #           value="param1=CONN1,CONN2;param2=CONN2" />
    # replacing:
    #   * PIPELINEVERSION with the version number
    #   * PlotName with the 'name' field of the plot
    #   * param<N> with the name of an input port of the plot
    #   * varname with the current name of a variable
    #   * ID<P> and PORT<P> with the module id and port name of the plot's
    #     input port for the associated parameter
    #   * CONN<M> with the ids of the connections tying the plot input port to
    #     the variable set to this port
    #
    # This assumes that:
    #   * Plot names don't change (and are not localized)
    #   * Plot, port and variable names don't contain ';' or '='
    #
    # Parameters which are not set are simply omitted from the list
    _RECIPE_KEY = 'dat-recipe'
    _PORTMAP_KEY = 'dat-ports'
    _VARMAP_KEY = 'dat-vars'

    @staticmethod
    def _build_annotation_recipe(recipe):
        """Builds the annotation value representation of a recipe.
        """
        value = recipe.plot.name
        for param, variable in recipe.variables.iteritems():
            value += ';%s=%s' % (param, variable.name)
        return value

    @staticmethod
    def _read_annotation_recipe(vistraildata, value):
        """Reads a recipe from its annotation value representation.
        """
        value = value.split(';')
        try:
            plot = GlobalManager.get_plot(value[0]) # Might raise KeyError
            variables = dict()
            for assignment in value[1:]:
                param, varname = assignment.split('=') # Might raise ValueError
                variables[param] = vistraildata.get_variable(varname)
            return DATRecipe(plot, variables)
        except (KeyError, ValueError):
            return None

    @staticmethod
    def _build_annotation_portmap(port_map):
        """Builds the annotation value representation of a port_map.
        """
        value = []
        for param, portlist in port_map.iteritems():
            value.append(
                    "%s=%s" % (
                            param,
                            ','.join('%d:%s' % (mod_id, portname)
                                     for mod_id, portname in portlist)))
        return ';'.join(value)

    @staticmethod
    def _read_annotation_portmap(value):
        """Reads a port_map from its annotation value representation.
        """
        try:
            port_map = dict()
            dv = value.split(';')
            for mapping in dv:
                param, ports = mapping.split('=')
                if not ports:
                    port_map[param] = []
                    continue
                ports = ports.split(',')
                portlist = []
                for port in ports:
                    port_ = port.split(':')
                    if len(port_) != 2:
                        raise ValueError
                    portlist.append((int(port_[0]), port_[1]))
                            # Might raise ValueError
                port_map[param] = portlist
            return port_map
        except ValueError:
            return None

    @staticmethod
    def _build_annotation_varmap(var_map):
        """Builds the annotation value representation of a var_map.
        """
        value = []
        for param, conn_list in var_map.iteritems():
            value.append(
                    "%s=%s" % (
                            param,
                            ','.join('%d' % conn_id
                                     for conn_id in conn_list)))
        return ';'.join(value)

    @staticmethod
    def _read_annotation_varmap(value):
        """Reads a var_map from its annotation value representation.
        """
        try:
            var_map = dict()
            dv = value.split(';')
            for mapping in dv:
                param, conns = mapping.split('=')
                if not conns:
                    var_map[param] = []
                    continue
                ports = conns.split(',')
                conn_list = []
                for port in ports:
                    conn_list.append(int(port))
                            # Might raise ValueError
                var_map[param] = conn_list
            return var_map
        except ValueError:
            return None

    def __init__(self, controller):
        """Initial setup of the VistrailData.

        Discovers plots and variable loaders from packages and registers
        notifications for packages loaded in the future.
        """
        self._controller = controller
        self._spreadsheet_tab = None

        self._variables = dict()

        self._cell_to_version = dict() # CellInformation -> int
        self._version_to_pipeline = dict() # int -> PipelineInformation
        self._cell_to_pipeline = dict() # CellInformation-> PipelineInformation

        app = get_vistrails_application()

        # dat_new_variable(varname: str)
        app.create_notification('dat_new_variable')
        # dat_removed_variable(varname: str)
        app.create_notification('dat_removed_variable')

        # Load variables from tagged versions
        if self._controller.vistrail.has_tag_str('dat-vars'):
            tagmap = self._controller.vistrail.get_tagMap()
            for version, tag in tagmap.iteritems():
                if tag.startswith('dat-var-'):
                    varname = tag[8:]
                    # Get the type from the OutputPort module's spec input port
                    type = Variable.read_type(
                            self._controller.vistrail.getPipeline(version))
                    if type is None:
                        warnings.warn("Found invalid DAT variable pipeline "
                                      "%r, ignored" % tag)
                    else:
                        variable = Variable.VariableInformation(
                                varname, self._controller, type)

                        self._variables[varname] = variable
                        self._add_variable(varname)

        # Load mappings from annotations
        annotations = self._controller.vistrail.action_annotations
        # First, read the recipes
        for an in annotations:
            if an.key == self._RECIPE_KEY:
                version = an.action_id
                recipe = self._read_annotation_recipe(self, an.value)
                if recipe is not None:
                    pipeline = PipelineInformation(version, recipe)
                    self._version_to_pipeline[version] = pipeline
        # Then, read the port maps
        for an in annotations:
            if an.key == self._PORTMAP_KEY:
                pipeline = self._version_to_pipeline[an.action_id]
                if not pipeline:
                    # Purge the lone port map
                    warnings.warn("Found a DAT port map annotation with not "
                                  "associated recipe -- removing")
                    self._controller.vistrail.set_action_annotation(
                            an.action_id,
                            an.key,
                            None)
                else:
                    port_map = self._read_annotation_portmap(an.value)
                    if port_map is not None:
                        pipeline.port_map = port_map
        # Finally, read the variable maps
        for an in annotations:
            if an.key == self._VARMAP_KEY:
                pipeline = self._version_to_pipeline[an.action_id]
                if not pipeline:
                    # Purge the lone var map
                    warnings.warn("Found a DAT variable map annotation with "
                                  "no associated recipe -- removing")
                    self._controller.vistrail.set_action_annotation(
                            an.action_id,
                            an.key,
                            None)
                else:
                    var_map = self._read_annotation_varmap(an.value)
                    if var_map is not None:
                        pipeline.varmap = var_map

    def _get_controller(self):
        return self._controller
    controller = property(_get_controller)

    def _get_spreadsheet_tab(self):
        if self._spreadsheet_tab is None:
            sh_window = spreadsheetController.findSpreadsheetWindow(
                    create=False)
            if sh_window is not None:
                tab_controller = sh_window.tabController
                tab = StandardWidgetSheetTab(
                        tab_controller,
                        allow_create_sheet=False)
                title = self._controller.name
                if not title:
                    title = "Untitled{ext}".format(
                            ext=vistrails_default_file_type())
                tabidx = tab_controller.addTabWidget(tab, title)
                self._spreadsheet_tab = tab
                VistrailManager._tabs[tab] = self
                tab_controller.setCurrentIndex(tabidx)
        return self._spreadsheet_tab
    spreadsheet_tab = property(_get_spreadsheet_tab)

    def update_spreadsheet_tab(self):
        """Updates the title of the spreadsheet tab.

        Called when a controller changes name.
        """
        tab = self.spreadsheet_tab
        if tab is not None:
            title = self._controller.name
            if not title:
                title = "Untitled{ext}".format(
                        ext=vistrails_default_file_type())
            tabWidget = tab.tabWidget
            tabWidget.setTabText(tabWidget.indexOf(tab), title)

    def new_variable(self, varname, variable):
        """Register a new Variable with DAT.

        This will materialize it in the pipeline and signal its creation.
        """
        if varname in self._variables:
            raise ValueError("A variable named %s already exists!")

        # Materialize the Variable in the Vistrail
        variable = variable.perform_operations(varname)

        self._variables[varname] = variable

        self._add_variable(varname)

    def _add_variable(self, varname, renamed_from=None):
        if renamed_from is not None:
            # Variable was renamed -- reflect this change on the annotations
            for pipeline in self._version_to_pipeline.itervalues():
                if any(
                        v.name == varname
                        for v in pipeline.recipe.variables.itervalues()):
                    self._controller.vistrail.set_action_annotation(
                            pipeline.version,
                            self._RECIPE_KEY,
                            self._build_annotation_recipe(pipeline.recipe))

        get_vistrails_application().send_notification(
                'dat_new_variable',
                self._controller,
                varname,
                renamed_from=renamed_from)

    def _remove_variable(self, varname, renamed_to=None):
        get_vistrails_application().send_notification(
                'dat_removed_variable',
                self._controller,
                varname,
                renamed_to=renamed_to)

        if renamed_to is None:
            # A variable was removed!
            # We'll remove all the mappings that used it
            to_remove = set([])
            for pipeline in self._version_to_pipeline.itervalues():
                if any(
                        v.name == varname
                        for v in pipeline.recipe.variables.itervalues()):
                    to_remove.add(pipeline.version)
            if to_remove:
                warnings.warn(
                        "Variable %r was used in %d pipelines!" % (
                                varname, len(to_remove)))
            for version in to_remove:
                del self._version_to_pipeline[version]

                # Remove the annotations from the vistrail
                for key in (
                        self._RECIPE_KEY, self._PORTMAP_KEY, self._VARMAP_KEY):
                    self._controller.vistrail.set_action_annotation(
                            version,
                            key,
                            None)

            cell_to_remove = []
            for cellInfo, version in self._cell_to_version.iteritems():
                if version in to_remove:
                    cell_to_remove.append(cellInfo)
            for cellInfo in cell_to_remove:
                del self._cell_to_version[cellInfo]
                del self._cell_to_pipeline[cellInfo]

    def remove_variable(self, varname):
        """Remove a Variable from DAT.

        This will remove the associated version in the vistrail and signal its
        destruction.
        """
        self._remove_variable(varname)

        variable = self._variables.pop(varname)
        variable.remove()

    def rename_variable(self, old_varname, new_varname):
        """Rename a Variable.

        This will update the tag on the associated version.

        Observers will get notified that a Variable was deleted and another
        added.
        """
        self._remove_variable(old_varname, renamed_to=new_varname)

        variable = self._variables.pop(old_varname)
        self._variables[new_varname] = variable
        variable.rename(new_varname)

        self._add_variable(new_varname, renamed_from=old_varname)

    def get_variable(self, varname):
        return self._variables.get(varname)

    def _get_variables(self):
        return self._variables.iterkeys()
    variables = property(_get_variables)

    def created_pipeline(self, cellInfo, pipeline):
        """Registers a new pipeline as being the result of a DAT recipe.

        We now know that this pipeline was created in the given cell from this
        plot and these parameters.

        The version will get annotated with the DAT metadata, allowing it to be
        updated later.
        """
        try:
            p = self._version_to_pipeline[pipeline.version]
            if p == pipeline:
                return # Ok I guess
            warnings.warn(
                    "A new pipeline was created with a previously known "
                    "version!\n"
                    "  version=%r\n"
                    "  old recipe=%r\n"
                    "  new recipe=%r\n"
                    "replacing..." % (
                    pipeline.version,
                    p.recipe,
                    pipeline.recipe))
        except KeyError:
            pass
        self._cell_to_version[cellInfo] = pipeline.version
        self._version_to_pipeline[pipeline.version] = pipeline
        self._cell_to_pipeline[cellInfo] = pipeline

        # Add the annotation in the vistrail
        self._controller.vistrail.set_action_annotation(
                pipeline.version,
                self._RECIPE_KEY,
                self._build_annotation_recipe(pipeline.recipe))

        self._controller.vistrail.set_action_annotation(
                pipeline.version,
                self._PORTMAP_KEY,
                self._build_annotation_portmap(pipeline.port_map))

        self._controller.vistrail.set_action_annotation(
                pipeline.version,
                self._VARMAP_KEY,
                self._build_annotation_varmap(pipeline.var_map))

    def get_pipeline(self, param):
        """Get the pipeline information for a given cell or version.

        Returns None if nothing is found.
        """
        if isinstance(param, int):
            return self._version_to_pipeline.get(param, None)
        else:
            return self._cell_to_pipeline.get(param, None)

    def _get_all_pipelines(self):
        return self._version_to_pipeline.itervalues()
    all_pipelines = property(_get_all_pipelines)


class VistrailManager(object):
    """Keeps a list of VistrailData objects.

    This singleton keeps a VistrailData object for each currently opened
    vistrail.
    """
    def __init__(self):
        self._vistrails = dict() # Controller -> VistrailData
        self._tabs = dict() # SpreadsheetTab -> VistrailData
        self._current_controller = None

    def init(self):
        """Initialization function, called when the application is created.

        This is not done at module-import time to avoid complex import-order
        issues.
        """
        app = get_vistrails_application()
        app.register_notification(
                'controller_changed',
                self.set_controller)
        app.register_notification(
                'controller_closed',
                self.forget_controller)
        bw = get_vistrails_application().builderWindow
        self.set_controller(bw.get_current_controller())

    def set_controller(self, controller):
        """Called through the notification mechanism.

        Changes the 'current' controller, building a VistrailData for it if
        necessary.
        """
        if controller == self._current_controller:
            # VisTrails lets this happen
            return

        self._current_controller = controller
        try:
            self._vistrails[controller]
            new = False
        except KeyError:
            self._vistrails[controller] = VistrailData(controller)
            new = True

        get_vistrails_application().send_notification(
                'dat_controller_changed',
                controller,
                new=new)

    def __call__(self, controller=None):
        """Accesses a VistrailData for a specific controller.

        If the controller is not specified, assume the current one.
        """
        if controller is None:
            controller = self._current_controller
        try:
            return self._vistrails[controller]
        except KeyError:
            warnings.warn("Unknown controller requested from "
                          "VistrailManager:\n  %r" % controller)
            vistraildata = VistrailData(controller)
            self._vistrails[controller] = vistraildata
            return vistraildata

    def from_spreadsheet_tab(self, tab):
        return self._tabs.get(tab)

    def forget_controller(self, controller):
        """Removes the data for a specific controller.

        Called when a controller is closed.
        """
        title = controller.name
        if not title:
            title = "Untitled{ext}".format(
                    ext=vistrails_default_file_type())
        try:
            vistraildata = self._vistrails[controller]
        except KeyError:
            return
        else:
            # Remove the spreadsheet
            spreadsheet_tab = vistraildata.spreadsheet_tab
            spreadsheet_tab.tabWidget.deleteSheet(spreadsheet_tab)

            del self._vistrails[controller]

VistrailManager = VistrailManager()
