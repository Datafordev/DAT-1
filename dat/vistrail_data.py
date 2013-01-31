import warnings

from dat import DATRecipe, PipelineInformation
from dat.global_data import GlobalManager
from dat.vistrails_interface import Variable

from vistrails.core.application import get_vistrails_application


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
    # replacing:
    #   * PIPELINEVERSION with the version number
    #   * PlotName with the 'name' field of the plot
    #   * param<N> with the name of an input port of the plot
    #   * varname with the current name of a variable
    #   * ID<P> and PORT<P> with the module id and port name of the plot's
    #     input for the associated parameter
    #
    # This assumes that:
    #   * Plot names don't change (and are not localized)
    #   * Plot, port and variable names don't contain ';' or '='
    #
    # Parameters which are not set are simply omitted from the list
    _RECIPE_KEY = 'dat-recipe'
    _PORTMAP_KEY = 'dat-ports'

    # TODO-dat : test coverage of these 4 methods

    @staticmethod
    def _build_annotation_recipe(recipe):
        value = recipe.plot.name
        for param, variable in recipe.variables.iteritems():
            value += ';%s=%s' % (param, variable.name)
        return value

    @staticmethod
    def _read_annotation_recipe(vistraildata, value):
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
    def _build_annotation_portmap(portmap):
        value = []
        for param, portlist in portmap.iteritems():
            value.append(
                    "%s=%s" % (
                            param,
                            ','.join('%d:%s' % (mod_id, portname)
                                     for mod_id, portname in portlist)))
        return ';'.join(value)

    @staticmethod
    def _read_annotation_portmap(value):
        try:
            portmap = dict()
            dv = value.split(';')
            for mapping in dv:
                param, ports = mapping.split('=')
                if not ports:
                    portmap[param] = []
                    continue
                ports = ports.split(',')
                portlist = []
                for port in ports:
                    port_ = port.split(':')
                    if len(port_) != 2:
                        raise ValueError
                    portlist.append((int(port_[0]), port_[1]))
                            # Might raise ValueError
                portmap[param] = portlist
            return portmap
        except ValueError:
            return None

    def __init__(self, controller):
        """Initial setup of the VistrailData.

        Discovers plots and variable loaders from packages and registers
        notifications for packages loaded in the future.
        """
        self._controller = controller

        self._variables = dict()

        self._pipeline_to_recipe = dict() # PipelineInformation -> DATRecipe
        self._recipe_to_pipeline = dict() # DATRecipe -> PipelineInformation
        self._pipeline_to_portmap = dict() # PipelineInformation -> portmap
        # portmap: {param: [(mod_id: int, portname: str)]}

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
                pipeline = PipelineInformation(an.action_id)
                recipe = self._read_annotation_recipe(self, an.value)
                if recipe is not None:
                    self._pipeline_to_recipe[pipeline] = recipe
                    self._recipe_to_pipeline[recipe] = pipeline
        # Then, read the port maps
        for an in annotations:
            if an.key == self._PORTMAP_KEY:
                pipeline = PipelineInformation(an.action_id)
                recipe = self._pipeline_to_recipe[pipeline]
                if not recipe:
                    # Purge the lone port map
                    warnings.warn("Found a DAT port map annotation with not "
                                  "associated recipe -- removing")
                    self._controller.vistrail.set_action_annotation(
                            an.action_id,
                            an.key,
                            None)
                else:
                    portmap = self._read_annotation_portmap(an.value)
                    if portmap is not None:
                        self._pipeline_to_portmap[pipeline] = portmap

    def _get_controller(self):
        return self._controller
    controller = property(_get_controller)

    def new_variable(self, varname, variable):
        """Register a new Variable with DAT.
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
            for recipe, pipeline in self._recipe_to_pipeline.iteritems():
                if any(
                        variable.name == varname
                        for variable in recipe.variables.itervalues()):
                    self._controller.vistrail.set_action_annotation(
                            pipeline.version,
                            self._RECIPE_KEY,
                            self._build_annotation_recipe(recipe))

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
            to_remove = []
            for recipe in self._recipe_to_pipeline.iterkeys():
                if any(
                        variable.name == varname
                        for variable in recipe.variables.itervalues()):
                    to_remove.append(recipe)
            if to_remove:
                warnings.warn(
                        "Variable %r was used in %d pipelines!" % (
                                varname, len(to_remove)))
            for recipe in to_remove:
                pipeline = self._recipe_to_pipeline.pop(recipe)
                del self._pipeline_to_recipe[pipeline]

                # Remove the annotation from the current vistrail
                self._controller.vistrail.set_action_annotation(
                        pipeline.version,
                        self._RECIPE_KEY,
                        None)

    def remove_variable(self, varname):
        """Remove a Variable from DAT.
        """
        self._remove_variable(varname)

        variable = self._variables.pop(varname)
        variable.remove()

    def rename_variable(self, old_varname, new_varname):
        """Rename a Variable.

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

    def created_pipeline(self, recipe, pipeline, portmap=None):
        """Registers a new pipeline as being the result of a DAT recipe.

        We now know that this pipeline was created from this plot and
        parameters, so we will display an overlay showing these on every cell
        created from that pipeline.
        """
        try:
            p = self._recipe_to_pipeline[recipe]
            if p != pipeline:
                def print_loc(l):
                    if hasattr(l, 'name') and l.name:
                        return l.name
                    else:
                        return str(l)
                warnings.warn(
                        "A new pipeline with a known recipe was created\n"
                        "Pipelines:\n"
                        "    %s version=%s\n"
                        "    %s version=%s" % (
                        print_loc(p.locator), p.version,
                        print_loc(pipeline.locator), pipeline.version))
        except KeyError:
            pass
        self._pipeline_to_recipe[pipeline] = recipe
        self._recipe_to_pipeline[recipe] = pipeline

        # Add the annotation in the vistrail
        self._controller.vistrail.set_action_annotation(
                pipeline.version,
                self._RECIPE_KEY,
                self._build_annotation_recipe(recipe))

        if portmap is not None:
            self._controller.vistrail.set_action_annotation(
                    pipeline.version,
                    self._PORTMAP_KEY,
                    self._build_annotation_portmap(portmap))
            self._pipeline_to_portmap[pipeline] = portmap

    def get_recipe(self, pipeline):
        return self._pipeline_to_recipe.get(pipeline, None)

    def get_pipeline(self, recipe):
        return self._recipe_to_pipeline.get(recipe, None)

    def get_portmap(self, pipeline):
        return self._pipeline_to_portmap.get(pipeline, None)


class VistrailManager(object):
    """Keeps a list of VistrailData objects.

    This singleton keeps a VistrailData object for each currently opened
    vistrail.
    """
    def __init__(self):
        self._vistrails = dict() # Controller -> VistrailData
        self._current_controller = None

    def init(self):
        get_vistrails_application().register_notification(
                'controller_changed',
                self.set_controller)
        bw = get_vistrails_application().builderWindow
        self.set_controller(bw.get_current_controller())

    def set_controller(self, controller):
        if controller == self._current_controller:
            # VisTrails lets this happen
            return

        self._current_controller = controller
        try:
            self._vistrails[controller]
        except KeyError:
            self._vistrails[controller] = VistrailData(controller)

        get_vistrails_application().send_notification(
                'dat_controller_changed',
                controller)

    def __call__(self, controller=None):
        if controller is None:
            controller = self._current_controller
        try:
            return self._vistrails[controller]
        except KeyError:
            warnings.warn("Unknown controller requested from "
                          "VistrailManager:\n  %r" % controller)
            vistraildata = VistrailData(controller)
            self._vistrail[controller] = vistraildata
            return vistraildata

VistrailManager = VistrailManager()