"""Pipeline.py - an ordered set of modules to be executed

CellProfiler is distributed under the GNU General Public License.
See the accompanying file LICENSE for details.

Developed by the Broad Institute
Copyright 2003-2009

Please see the AUTHORS file for credits.

Website: http://www.cellprofiler.org
"""
__version = "$Revision$"

import hashlib
import numpy
import scipy.io.matlab
import os
import StringIO
import sys
import tempfile
import datetime
import traceback
import cellprofiler.cpmodule
import cellprofiler.preferences
from cellprofiler.matlab.cputils import new_string_cell_array,get_matlab_instance
from cellprofiler.matlab.cputils import s_cell_fun,make_cell_struct_dtype
from cellprofiler.matlab.cputils import load_into_matlab,get_int_from_matlab
from cellprofiler.matlab.cputils import encapsulate_strings_in_arrays
import cellprofiler.cpimage
import cellprofiler.measurements as cpmeas
import cellprofiler.objects
import cellprofiler.workspace as cpw

'''The measurement name of the image number'''
IMAGE_NUMBER = "ImageNumber"
CURRENT = 'Current'
NUMBER_OF_IMAGE_SETS     = 'NumberOfImageSets'
NUMBER_OF_MODULES        = 'NumberOfModules'
SET_BEING_ANALYZED       = 'SetBeingAnalyzed'
SAVE_OUTPUT_HOW_OFTEN    = 'SaveOutputHowOften'
TIME_STARTED             = 'TimeStarted'
STARTING_IMAGE_SET       = 'StartingImageSet'
STARTUP_DIRECTORY        = 'StartupDirectory'
DEFAULT_MODULE_DIRECTORY = 'DefaultModuleDirectory'
DEFAULT_IMAGE_DIRECTORY  = 'DefaultImageDirectory'
DEFAULT_OUTPUT_DIRECTORY = 'DefaultOutputDirectory'
IMAGE_TOOLS_FILENAMES    = 'ImageToolsFilenames'
IMAGE_TOOL_HELP          = 'ImageToolHelp'
PREFERENCES              = 'Preferences'
PIXEL_SIZE               = 'PixelSize'
SKIP_ERRORS              = 'SkipErrors'
INTENSITY_COLOR_MAP      = 'IntensityColorMap'
LABEL_COLOR_MAP          = 'LabelColorMap'
STRIP_PIPELINE           = 'StripPipeline'
DISPLAY_MODE_VALUE       = 'DisplayModeValue'
DISPLAY_WINDOWS          = 'DisplayWindows'
FONT_SIZE                = 'FontSize'
IMAGES                   = 'Images'
MEASUREMENTS             = 'Measurements'
PIPELINE                 = 'Pipeline'    
SETTINGS                  = 'Settings'
VARIABLE_VALUES           = 'VariableValues'
VARIABLE_INFO_TYPES       = 'VariableInfoTypes'
MODULE_NAMES              = 'ModuleNames'
PIXEL_SIZE                = 'PixelSize'
NUMBERS_OF_VARIABLES      = 'NumbersOfVariables'
VARIABLE_REVISION_NUMBERS = 'VariableRevisionNumbers'
MODULE_REVISION_NUMBERS   = 'ModuleRevisionNumbers'
MODULE_NOTES              = 'ModuleNotes'
CURRENT_MODULE_NUMBER     = 'CurrentModuleNumber'
SETTINGS_DTYPE = numpy.dtype([(VARIABLE_VALUES, '|O4'), 
                            (VARIABLE_INFO_TYPES, '|O4'), 
                            (MODULE_NAMES, '|O4'), 
                            (NUMBERS_OF_VARIABLES, '|O4'), 
                            (PIXEL_SIZE, '|O4'), 
                            (VARIABLE_REVISION_NUMBERS, '|O4'), 
                            (MODULE_REVISION_NUMBERS, '|O4'), 
                            (MODULE_NOTES, '|O4')])
CURRENT_DTYPE = make_cell_struct_dtype([ NUMBER_OF_IMAGE_SETS,SET_BEING_ANALYZED,NUMBER_OF_MODULES, 
                                     SAVE_OUTPUT_HOW_OFTEN,TIME_STARTED, STARTING_IMAGE_SET,
                                     STARTUP_DIRECTORY, DEFAULT_OUTPUT_DIRECTORY, DEFAULT_IMAGE_DIRECTORY, 
                                     IMAGE_TOOLS_FILENAMES, IMAGE_TOOL_HELP])
PREFERENCES_DTYPE = make_cell_struct_dtype([PIXEL_SIZE, DEFAULT_MODULE_DIRECTORY, DEFAULT_OUTPUT_DIRECTORY, 
                                         DEFAULT_IMAGE_DIRECTORY, INTENSITY_COLOR_MAP, LABEL_COLOR_MAP,
                                         STRIP_PIPELINE, SKIP_ERRORS, DISPLAY_MODE_VALUE, FONT_SIZE,
                                         DISPLAY_WINDOWS])
 
def add_matlab_images(handles,image_set):
    """Add any images from the handles to the image set
    Generally, the handles have images added as they get returned from a Matlab module.
    You can use this to update the image set and capture them.
    """
    matlab = get_matlab_instance()
    pipeline_fields = matlab.fields(handles.Pipeline)
    provider_set = set([x.name for x in image_set.providers])
    image_fields = set()
    crop_fields = set()
    for i in range(0,int(matlab.length(pipeline_fields)[0,0])):
        field = matlab.cell2mat(pipeline_fields[i])
        if field.startswith('CropMask'):
            crop_fields.add(field)
        elif field.startswith('Segmented') or field.startswith('UneditedSegmented') or field.startswith('SmallRemovedSegmented'):
            continue
        elif field.startswith('Pathname') or field.startswith('FileList') or field.startswith('Filename'):
            if not image_set.legacy_fields.has_key(field):
                value = matlab.getfield(handles.Pipeline,field)
                if not (isinstance(value,str) or isinstance(value,unicode)):
                    # The two supported types: string/unicode or cell array of strings
                    count = matlab.length(value)
                    new_value = numpy.ndarray((1,count),dtype='object')
                    for j in range(0,count):
                        new_value[0,j] = matlab.cell2mat(value[j])
                    value = new_value 
                image_set.legacy_fields[field] = value
        elif not field in provider_set:
            image_fields.add(field)
    for field in image_fields:
        image = cellprofiler.image.Image()
        image.Image = matlab.getfield(handles.Pipeline,field)
        crop_field = 'CropMask'+field
        if crop_field in crop_fields:
            image.Mask = matlab.getfield(handles.Pipeline,crop_field)
        image_set.providers.append(cellprofiler.cpimage.VanillaImageProvider(field,image))
    number_of_image_sets = get_int_from_matlab(handles.Current.NumberOfImageSets)
    if (not image_set.legacy_fields.has_key(NUMBER_OF_IMAGE_SETS)) or number_of_image_sets < image_set.legacy_fields[NUMBER_OF_IMAGE_SETS]:
        image_set.legacy_fields[NUMBER_OF_IMAGE_SETS] = number_of_image_sets

def add_matlab_objects(handles,object_set):
    """Add any objects from the handles to the object set
    You can use this to update the object set after calling a matlab module
    """
    matlab = get_matlab_instance()
    pipeline_fields = matlab.fields(handles.Pipeline)
    objects_names = set(object_set.get_object_names())
    segmented_fields = set()
    unedited_segmented_fields = set()
    small_removed_segmented_fields = set()
    for i in range(0,int(matlab.length(pipeline_fields)[0,0])):
        field = matlab.cell2mat(pipeline_fields[i])
        if field.startswith('Segmented'):
            segmented_fields.add(field)
        elif field.startswith('UneditedSegmented'):
            unedited_segmented_fields.add(field)
        elif field.startswith('SmallRemovedSegmented'):
            small_removed_segmented_fields.add(field)
    for field in segmented_fields:
        object_name = field.replace('Segmented','')
        if object_name in object_set.get_object_names():
            continue
        objects = cellprofiler.objects.Objects()
        objects.segmented = matlab.getfield(handles.Pipeline,field)
        unedited_field ='Unedited'+field
        small_removed_segmented_field = 'SmallRemoved'+field 
        if unedited_field in unedited_segmented_fields:
            objects.unedited_segmented = matlab.getfield(handles.Pipeline,unedited_field)
        if small_removed_segmented_field in small_removed_segmented_fields:
            objects.SmallRemovedSegmented = matlab.getfield(handles.Pipeline,small_removed_segmented_field)
        object_set.add_objects(objects,object_name)

def add_matlab_measurements(handles, measurements):
    """Get measurements made by Matlab and put them into our Python measurements object
    """
    matlab = get_matlab_instance()
    measurement_fields = matlab.fields(handles.Measurements)
    for i in range(0,int(matlab.length(measurement_fields)[0,0])):
        field = matlab.cell2mat(measurement_fields[i])
        object_measurements = matlab.getfield(handles.Measurements,field)
        object_fields = matlab.fields(object_measurements)
        for j in range(0,int(matlab.length(object_fields)[0,0])):
            feature = matlab.cell2mat(object_fields[j])
            if not measurements.has_current_measurements(field,feature):
                value = matlab.cell2mat(matlab.getfield(object_measurements,feature)[measurements.image_set_number-1])
                if not isinstance(value,numpy.ndarray) or numpy.product(value.shape) > 0:
                    # It's either not a numpy array (it's a string) or it's not the empty numpy array
                    # so add it to the measurements
                    measurements.add_measurement(field,feature,value)

def add_all_images(handles,image_set, object_set):
    """ Add all images to the handles structure passed
    
    Add images to the handles structure, for example in the Python sandwich.
    """
    images = {}
    for provider in image_set.providers:
        name = provider.name()
        image = image_set.get_image(name)
        images[name] = image.image
        if image.has_mask:
            images['CropMask'+name] = image.mask
    
    for object_name in object_set.object_names:
        objects = object_set.get_objects(object_name)
        images['Segmented'+object_name] = objects.segmented
        if objects.has_unedited_segmented():
            images['UneditedSegmented'+object_name] = objects.unedited_segmented
        if objects.has_small_removed_segmented():
            images['SmallRemovedSegmented'+object_name] = objects.small_removed_segmented
    
    npy_images = numpy.ndarray((1,1),dtype=make_cell_struct_dtype(images.keys()))
    for key,image in images.iteritems():
        npy_images[key][0,0] = image
    handles[PIPELINE]=npy_images

def add_all_measurements(handles, measurements):
    """Add all measurements from our measurements object into the numpy structure passed
    
    """
    measurements_dtype = make_cell_struct_dtype(measurements.get_object_names())
    npy_measurements = numpy.ndarray((1,1),dtype=measurements_dtype)
    handles[MEASUREMENTS]=npy_measurements
    for object_name in measurements.get_object_names():
        if object_name == cpmeas.EXPERIMENT:
            continue
        object_dtype = make_cell_struct_dtype(measurements.get_feature_names(object_name))
        object_measurements = numpy.ndarray((1,1),dtype=object_dtype)
        npy_measurements[object_name][0,0] = object_measurements
        for feature_name in measurements.get_feature_names(object_name):
            feature_measurements = numpy.ndarray((1,measurements.image_set_index+1),dtype='object')
            object_measurements[feature_name][0,0] = feature_measurements
            data = measurements.get_all_measurements(object_name,feature_name)
            for i in range(0,measurements.image_set_index+1):
                if data != None:
                    ddata = data[i]
                    if numpy.isscalar(ddata) and numpy.isreal(ddata):
                        feature_measurements[0,i] = numpy.array([ddata])
                    else:
                        feature_measurements[0,i] = ddata
                else:
                    feature_measurements[0, i] = np.array([0])
    if cpmeas.EXPERIMENT in measurements.object_names:
        object_dtype = make_cell_struct_dtype(measurements.get_feature_names(cpmeas.EXPERIMENT))
        experiment_measurements = numpy.ndarray((1,1), dtype=object_dtype)
        npy_measurements[cpmeas.EXPERIMENT][0,0] = experiment_measurements
        for feature_name in measurements.get_feature_names(cpmeas.EXPERIMENT):
            feature_measurements = numpy.ndarray((1,1),dtype='object')
            feature_measurements[0,0] = measurements.get_experiment_measurement(feature_name)
            experiment_measurements[feature_name][0,0] = feature_measurements

class Pipeline(object):
    """A pipeline represents the modules that a user has put together
    to analyze their images.
    
    """
    def __init__(self):
        self.__modules = [];
        self.__listeners = [];
        self.__measurement_columns = {}
        self.__measurement_column_hash = None
    
    def copy(self):
        '''Create a copy of the pipeline modules and settings'''
        fd = StringIO.StringIO()
        self.save(fd)
        pipeline = Pipeline()
        fd.seek(0)
        pipeline.load(fd)
        return pipeline
    
    def settings_hash(self):
        '''Return a hash of the module settings
        
        This function can be used to invalidate a cached calculation
        that's based on pipeline settings - if the settings change, the
        hash changes and the calculation must be performed again.
        
        We use secure hashing functions which are really good at avoiding
        collisions for small changes in data.
        '''
        h = hashlib.md5()
        for module in self.modules():
            h.update(module.module_name)
            for setting in module.settings():
                h.update(str(setting))
        return h.digest()
    
    def create_from_handles(self,handles):
        """Read a pipeline's modules out of the handles structure
        
        """
        self.__modules = [];
        settings = handles[SETTINGS][0,0]
        module_names = settings[MODULE_NAMES]
        module_count = module_names.shape[1]
        for module_num in range(1,module_count+1):
            idx = module_num-1
            module_name = module_names[0,idx][0]
            module = self.instantiate_module(module_name)
            try:
                module.create_from_handles(handles, module_num)
            except Exception,instance:
                traceback.print_exc()
                event = LoadExceptionEvent(instance,module)
                self.notify_listeners(event)
                if event.cancel_run:
                    return
                
            self.__modules.append(module)
        for module in self.__modules:
            module.on_post_load(self)
            
        self.notify_listeners(PipelineLoadedEvent())
    
    def instantiate_module(self,module_name):
        import cellprofiler.modules
        
        substitutions = cellprofiler.modules.get_module_substitutions()
        if substitutions.has_key(module_name):
            module = substitutions[module_name]()
        elif module_name.find('.') != -1:
            parts     = module_name.split('.')
            pkg_name  = '.'.join(parts[:-1])
            pkg       = __import__(pkg_name)
            module    = eval("%s()"%(module_name))
        else:
            module = cellprofiler.cpmodule.MatlabModule()
        return module
        
    def save_to_handles(self):
        """Create a numpy array representing this pipeline
        
        """
        settings = numpy.ndarray(shape=[1,1],dtype=SETTINGS_DTYPE)
        handles = {SETTINGS:settings }
        setting = settings[0,0]
        # The variables are a (modules,max # of variables) array of cells (objects)
        # where an empty cell is a (1,0) array of float64
        variable_count = max([len(module.settings()) for module in self.modules()])
        module_count = len(self.modules())
        setting[VARIABLE_VALUES] =          new_string_cell_array((module_count,variable_count))
        # The variable info types are similarly shaped
        setting[VARIABLE_INFO_TYPES] =      new_string_cell_array((module_count,variable_count))
        setting[MODULE_NAMES] =             new_string_cell_array((1,module_count))
        setting[NUMBERS_OF_VARIABLES] =     numpy.ndarray(shape=(1,module_count),dtype=numpy.dtype('uint8'))
        setting[PIXEL_SIZE] =               cellprofiler.preferences.get_pixel_size() 
        setting[VARIABLE_REVISION_NUMBERS] =numpy.ndarray(shape=(1,module_count),dtype=numpy.dtype('uint8'))
        setting[MODULE_REVISION_NUMBERS] =  numpy.ndarray(shape=(1,module_count),dtype=numpy.dtype('uint16'))
        setting[MODULE_NOTES] =             new_string_cell_array((1,module_count))
        for module in self.modules():
            module.save_to_handles(handles)
        return handles
    
    def load(self, fd_or_filename):
        """Load the pipeline from a file
        
        fd_or_filename - either the name of a file or a file-like object
        """
        handles=scipy.io.matlab.mio.loadmat(fd_or_filename, struct_as_record=True)
        self.create_from_handles(handles)
        
    def save(self, fd_or_filename):
        """Save the pipeline to a file
        
        fd_or_filename - either a file descriptor or the name of the file
        """
        handles = self.save_to_handles()
        scipy.io.matlab.mio.savemat(fd_or_filename,handles,format='5')
    
    def save_measurements(self,filename, measurements):
        """Save the measurements and the pipeline settings in a Matlab file
        
        filename     - name of file to create
        measurements - measurements structure that is the result of running the pipeline
        """
        handles = self.build_matlab_handles()
        add_all_measurements(handles, measurements)
        handles[CURRENT][NUMBER_OF_IMAGE_SETS][0,0] = float(measurements.image_set_number+1)
        handles[CURRENT][SET_BEING_ANALYZED][0,0] = float(measurements.image_set_number+1)
        #
        # For the output file, you have to bury it a little deeper - the root has to have
        # a single field named "handles"
        #
        root = {'handles':numpy.ndarray((1,1),dtype=make_cell_struct_dtype(handles.keys()))}
        for key,value in handles.iteritems():
            root['handles'][key][0,0]=value
        
        scipy.io.matlab.mio.savemat(filename,root,format='5',
                                    long_field_names=True)
    
    def load_pipeline_into_matlab(self, image_set=None, object_set=None, measurements=None):
        """Load the pipeline into the Matlab singleton and return the handles structure
        
        The handles structure has all of the goodies needed to run the pipeline including
        * Settings
        * Current (set up to run the first image with the first module
        * Measurements - filled in from measurements (TO_DO)
        * Pipeline - filled in from the image set (TO_DO)
        Returns the handles proxy
        """
        handles = self.build_matlab_handles(image_set, object_set, measurements)
        mat_handles = load_into_matlab(handles)
        
        matlab = get_matlab_instance()
        if not handles.has_key(MEASUREMENTS):
            mat_handles.Measurements = matlab.struct()
        if not handles.has_key(PIPELINE):
            mat_handles.Pipeline = matlab.struct()
        return mat_handles
    
    def build_matlab_handles(self, image_set = None, object_set = None, measurements=None):
        handles = self.save_to_handles()
        image_tools_dir = os.path.join(cellprofiler.preferences.cell_profiler_root_directory(),'ImageTools')
        if os.access(image_tools_dir, os.R_OK):
            image_tools = [str(os.path.split(os.path.splitext(filename)[0])[1])
                           for filename in os.listdir(image_tools_dir)
                           if os.path.splitext(filename)[1] == '.m']
        else:
            image_tools = []
        image_tools.insert(0,'Image tools')
        npy_image_tools = numpy.ndarray((1,len(image_tools)),dtype=numpy.dtype('object'))
        for tool,idx in zip(image_tools,range(0,len(image_tools))):
            npy_image_tools[0,idx] = tool
            
        current = numpy.ndarray(shape=[1,1],dtype=CURRENT_DTYPE)
        handles[CURRENT]=current
        current[NUMBER_OF_IMAGE_SETS][0,0]     = [(image_set != None and image_set.legacy_fields.has_key(NUMBER_OF_IMAGE_SETS) and image_set.legacy_fields[NUMBER_OF_IMAGE_SETS]) or 1]
        current[SET_BEING_ANALYZED][0,0]       = [(measurements and measurements.image_set_number) or 1]
        current[NUMBER_OF_MODULES][0,0]        = [len(self.__modules)]
        current[SAVE_OUTPUT_HOW_OFTEN][0,0]    = [1]
        current[TIME_STARTED][0,0]             = str(datetime.datetime.now())
        current[STARTING_IMAGE_SET][0,0]       = [1]
        current[STARTUP_DIRECTORY][0,0]        = cellprofiler.preferences.cell_profiler_root_directory()
        current[DEFAULT_OUTPUT_DIRECTORY][0,0] = cellprofiler.preferences.get_default_output_directory()
        current[DEFAULT_IMAGE_DIRECTORY][0,0]  = cellprofiler.preferences.get_default_image_directory()
        current[IMAGE_TOOLS_FILENAMES][0,0]    = npy_image_tools
        current[IMAGE_TOOL_HELP][0,0]          = []

        preferences = numpy.ndarray(shape=(1,1),dtype=PREFERENCES_DTYPE)
        handles[PREFERENCES] = preferences
        preferences[PIXEL_SIZE][0,0]               = cellprofiler.preferences.get_pixel_size()
        preferences[DEFAULT_MODULE_DIRECTORY][0,0] = cellprofiler.preferences.module_directory()
        preferences[DEFAULT_OUTPUT_DIRECTORY][0,0] = cellprofiler.preferences.get_default_output_directory()
        preferences[DEFAULT_IMAGE_DIRECTORY][0,0]  = cellprofiler.preferences.get_default_image_directory()
        preferences[INTENSITY_COLOR_MAP][0,0]      = 'gray'
        preferences[LABEL_COLOR_MAP][0,0]          = 'jet'
        preferences[STRIP_PIPELINE][0,0]           = 'Yes'                  # TODO - get from preferences
        preferences[SKIP_ERRORS][0,0]              = 'No'                   # TODO - get from preferences
        preferences[DISPLAY_MODE_VALUE][0,0]       = [1]                    # TODO - get from preferences
        preferences[FONT_SIZE][0,0]                = [10]                   # TODO - get from preferences
        preferences[DISPLAY_WINDOWS][0,0]          = [1 for module in self.__modules] # TODO - UI allowing user to choose whether to display a window
        
        images = {}
        if image_set:
            for provider in image_set.providers:
                image = image_set.get_image(provider.name)
                if image.image != None:
                    images[provider.name]=image.image
                if image.mask != None:
                    images['CropMask'+provider.name]=image.mask
            for key,value in image_set.legacy_fields.iteritems():
                if key != NUMBER_OF_IMAGE_SETS:
                    images[key]=value
                
        if object_set:
            for name,objects in object_set.all_objects:
                images['Segmented'+name]=objects.segmented
                if objects.has_unedited_segmented():
                    images['UneditedSegmented'+name] = objects.unedited_segmented
                if objects.has_small_removed_segmented():
                    images['SmallRemovedSegmented'+name] = objects.small_removed_segmented
                    
        if len(images):
            pipeline_dtype = make_cell_struct_dtype(images.keys())
            pipeline = numpy.ndarray((1,1),dtype=pipeline_dtype)
            handles[PIPELINE] = pipeline
            for name,image in images.items():
                pipeline[name][0,0] = images[name]

        no_measurements = (measurements == None or len(measurements.get_object_names())==0)
        if not no_measurements:
            measurements_dtype = make_cell_struct_dtype(measurements.get_object_names())
            npy_measurements = numpy.ndarray((1,1),dtype=measurements_dtype)
            handles['Measurements']=npy_measurements
            for object_name in measurements.get_object_names():
                object_dtype = make_cell_struct_dtype(measurements.get_feature_names(object_name))
                object_measurements = numpy.ndarray((1,1),dtype=object_dtype)
                npy_measurements[object_name][0,0] = object_measurements
                for feature_name in measurements.get_feature_names(object_name):
                    feature_measurements = numpy.ndarray((1,measurements.image_set_number),dtype='object')
                    object_measurements[feature_name][0,0] = feature_measurements
                    data = measurements.get_current_measurement(object_name,feature_name)
                    feature_measurements.fill(numpy.ndarray((0,),dtype=numpy.float64))
                    if data != None:
                        feature_measurements[0,measurements.image_set_number-1] = data
        return handles
    
    def run(self,
            frame = None, 
            image_set_start = 0, 
            image_set_end = None,
            grouping = None):
        """Run the pipeline
        
        Run the pipeline, returning the measurements made
        frame - the frame to be used when displaying graphics or None to
                run headless
        image_set_start - the index of the first image to be run
        image_set_end - the index of the last image to be run + 1
        grouping - a dictionary that gives the keys and values in the
                   grouping to run or None to run all groupings
        """
        measurements = cellprofiler.measurements.Measurements()
        for m in self.run_with_yield(frame, 
                                     image_set_start, 
                                     image_set_end,
                                     grouping):
            measurements = m
        return measurements

    def run_with_yield(self,frame = None, 
                       image_set_start = 0, 
                       image_set_end = None,
                       grouping = None):
        """Run the pipeline, yielding periodically to keep the GUI alive
        
        Run the pipeline, returning the measurements made
        """
        image_set_list = self.prepare_run(frame)
        if image_set_list == None:
            return
        
        keys, groupings = self.get_groupings(image_set_list)
        if grouping is not None:
            for key in grouping.keys():
                if key not in keys:
                    raise ValueError("The grouping key, %s, is not in the list of keys that specify a group: %s"%
                                     (key, keys))
            for key in keys:
                if key not in grouping.keys():
                    raise ValueError("The key, %s, is missing from the list of keys that specify a group: %s"%
                                     (key, keys))
        measurements = None
        first_set = True
        matlab_initialized = False
        
        for grouping_keys, image_numbers in groupings:
            #
            # Loop over groups
            #
            match = True
            for key in keys:
                if grouping is not None and grouping[key] != grouping_keys[key]:
                    match = False
                    break
            if not match:
                continue
            prepare_group_has_run = False
            for image_number in image_numbers:
                #
                # Loop over image sets within groups
                #
                if image_number < image_set_start:
                    continue
                if image_set_end is not None and image_number > image_set_end:
                    continue
                if not prepare_group_has_run:
                    if not self.prepare_group(image_set_list, 
                                              grouping_keys,
                                              image_numbers):
                        return
                    prepare_group_has_run = True
                if first_set:
                    measurements = cpmeas.Measurements(
                        image_set_start=image_number-1)
                else:
                    measurements.next_image_set(image_number)
                measurements.add_image_measurement(IMAGE_NUMBER, image_number)
                numberof_windows = 0;
                slot_number = 0
                object_set = cellprofiler.objects.ObjectSet()
                image_set = image_set_list.get_image_set(image_number-1)
                outlines = {}
                for module in self.modules():
                    module_error_measurement = 'ModuleError_%02d%s'%(module.module_num,module.module_name)
                    execution_time_measurement = 'ExecutionTime_%02d%s'%(module.module_num,module.module_name)
                    failure = 1
                    if (not matlab_initialized) and module.needs_matlab():
                        self.set_matlab_path()
                        matlab_initialized = True
                    try:
                        workspace = cpw.Workspace(self,
                                                  module,
                                                  image_set,
                                                  object_set,
                                                  measurements,
                                                  image_set_list,
                                                  frame,
                                                  outlines = outlines)
                        t0 = datetime.datetime.now()
                        module.run(workspace)
                        t1 = datetime.datetime.now()
                        workspace.refresh()
                        failure = 0
                    except Exception,instance:
                        traceback.print_exc()
                        event = RunExceptionEvent(instance,module)
                        self.notify_listeners(event)
                        if event.cancel_run:
                            return
                        
                    # Paradox: ExportToDatabase must write these columns in order 
                    #  to complete, but in order to do so, the module needs to 
                    #  have already completed. So we don't report them for it.
                    if (module.module_name != 'Restart' and 
                        module.module_name != 'ExportToDatabase'):
                        measurements.add_measurement('Image',
                                                     module_error_measurement,
                                                     numpy.array([failure]));
                        delta = t1-t0
                        delta_sec = (delta.days * 24 * 60 *60 + delta.seconds +
                                     float(delta.microseconds) / 1000. / 1000.)
                        measurements.add_measurement('Image',
                                                     execution_time_measurement,
                                                     numpy.array([delta_sec]))
                    yield measurements
                first_set = False
                image_set_list.purge_image_set(image_number-1)
            if prepare_group_has_run:
                if not self.post_group(workspace, grouping_keys):
                    return
                
        self.post_run(measurements, image_set_list, frame)
        
    def prepare_run(self, frame):
        """Do "prepare_run" on each module to initialize the image_set_list
        
        returns the image_set_list or None if an exception was thrown
        """
        image_set_list = cellprofiler.cpimage.ImageSetList()
        
        for module in self.modules():
            try:
                if not module.prepare_run(self, image_set_list, frame):
                    return None
            except Exception,instance:
                traceback.print_exc()
                event = RunExceptionEvent(instance,module)
                self.notify_listeners(event)
                if event.cancel_run:
                    return None
        assert not any([len(image_set_list.get_image_set(i).providers)
                        for i in range(image_set_list.count())]),\
               "Image providers cannot be added in prepare_run. Please add them in prepare_group instead"
        return image_set_list
    
    def post_run(self, measurements, image_set_list, frame):
        """Do "post_run" on each module to perform aggregation tasks
        
        measurements - the measurements for the run
        image_set_list - the image set list for the run
        frame - the topmost frame window or None if no GUI
        """
        for module in self.modules():
            workspace = cpw.Workspace(self,
                                      module,
                                      None,
                                      None,
                                      measurements,
                                      image_set_list,
                                      frame)
            workspace.refresh()
            try:
                module.post_run(workspace)
            except Exception, instance:
                traceback.print_exc()
                event = RunExceptionEvent(instance, module)
                self.notify_listeners(event)
                if event.cancel_run:
                    return
    
    def prepare_to_create_batch(self, image_set_list, fn_alter_path):
        '''Prepare to create a batch file
        
        This function is called when CellProfiler is about to create a
        file for batch processing. It will pickle the image set list's
        "legacy_fields" dictionary. This callback lets a module prepare for
        saving.
        
        image_set_list - the image set list to be saved
        fn_alter_path - this is a function that takes a pathname on the local
                        host and returns a pathname on the remote host. It
                        handles issues such as replacing backslashes and
                        mapping mountpoints. It should be called for every
                        pathname stored in the settings or legacy fields.
        '''
        for module in self.modules():
            try:
                module.prepare_to_create_batch(self, image_set_list, 
                                               fn_alter_path)
            except Exception, instance:
                traceback.print_exc()
                event = RunExceptionEvent(instance, module)
                self.notify_listeners(event)
                if event.cancel_run:
                    return
    
    def get_groupings(self, image_set_list):
        '''Return the image groupings of the image sets in an image set list
        
        returns a tuple of key_names and group_list:
        key_names - the names of the keys that identify the groupings
        group_list - a sequence composed of two-tuples.
                     the first element of the tuple has the values for
                     the key_names for this group.
                     the second element of the tuple is a sequence of
                     image numbers comprising the image sets of the group
        For instance, an experiment might have key_names of 'Metadata_Row'
        and 'Metadata_Column' and a group_list of:
        [ (('A','01'), [0,96,192]),
          (('A','02'), [1,97,193]),... ]
        '''
        groupings = None
        grouping_module = None
        for module in self.modules():
            new_groupings = module.get_groupings(image_set_list)
            if new_groupings is None:
                continue
            if groupings is None:
                groupings = new_groupings
                grouping_module = module
            else:
                raise ValueError("The pipeline has two grouping modules: # %d "
                                 "(%s) and # %d (%s)" %
                                 (grouping_module.module_num, 
                                  grouping_module.module_name,
                                  module.module_num,
                                  module.module_name))
        if groupings is None:
            return ((), (((),range(1, image_set_list.count()+1)),))
        return groupings
    
    def prepare_group(self, image_set_list, grouping, image_numbers):
        '''Prepare to start processing a new group
        
        image_set_list - the image set list for the run
        grouping - a dictionary giving the keys and values for the group
        
        returns true if the group should be run
        '''
        for module in self.modules():
            try:
                module.prepare_group(self, image_set_list, grouping, 
                                     image_numbers)
            except Exception, instance:
                traceback.print_exc()
                event = RunExceptionEvent(instance, module)
                self.notify_listeners(event)
                if event.cancel_run:
                    return False
        return True
    
    def post_group(self, workspace, grouping):
        '''Do post-processing after a group completes
        
        workspace - the last workspace run
        '''
        for module in self.modules():
            try:
                module.post_group(workspace, grouping)
            except Exception, instance:
                traceback.print_exc()
                event = RunExceptionEvent(instance, module)
                self.notify_listeners(event)
                if event.cancel_run:
                    return False
        return True
    
    def in_batch_mode(self):
        '''Return True if the pipeline is in batch mode'''
        for module in self.modules():
            batch_mode = module.in_batch_mode()
            if batch_mode is not None:
                return batch_mode

    def set_matlab_path(self):
        matlab = get_matlab_instance()
        matlab.path(os.path.join(cellprofiler.preferences.cell_profiler_root_directory(),'DataTools'),matlab.path())
        matlab.path(os.path.join(cellprofiler.preferences.cell_profiler_root_directory(),'ImageTools'),matlab.path())
        matlab.path(os.path.join(cellprofiler.preferences.cell_profiler_root_directory(),'CPsubfunctions'),matlab.path())
        matlab.path(cellprofiler.preferences.module_directory(),matlab.path())
        matlab.path(cellprofiler.preferences.cell_profiler_root_directory(),matlab.path())

    def clear(self):
        old_modules = self.__modules
        self.__modules = []
        for module in old_modules:
            module.delete()
        self.notify_listeners(PipelineClearedEvent())
    
    def move_module(self,module_num,direction):
        """Move module # ModuleNum either DIRECTION_UP or DIRECTION_DOWN in the list
        
        Move the 1-indexed module either up one or down one in the list, displacing
        the other modules in the list
        """
        idx=module_num-1
        if direction == DIRECTION_DOWN:
            if module_num >= len(self.__modules):
                raise ValueError('%(ModuleNum)d is at or after the last module in the pipeline and can''t move down'%(locals()))
            module = self.__modules[idx]
            new_module_num = module_num+1
            module.set_module_num(module_num+1)
            next_module = self.__modules[idx+1]
            next_module.set_module_num(module_num)
            self.__modules[idx]=next_module
            self.__modules[idx+1]=module
        elif direction == DIRECTION_UP:
            if module_num <= 1:
                raise ValueError('The module is at the top of the pipeline and can''t move up')
            module = self.__modules[idx]
            prev_module = self.__modules[idx-1]
            new_module_num = prev_module.module_num
            module.module_num = new_module_num
            prev_module.module_num = module_num
            self.__modules[idx]=self.__modules[idx-1]
            self.__modules[idx-1]=module
        else:
            raise ValueError('Unknown direction: %s'%(direction))    
        self.notify_listeners(ModuleMovedPipelineEvent(new_module_num,direction))
        
    def modules(self):
        return self.__modules
    
    def module(self,module_num):
        module = self.__modules[module_num-1]
        assert module.module_num==module_num,'Misnumbered module. Expected %d, got %d'%(module_num,module.module_num)
        return module
    
    def add_module(self,new_module):
        """Insert a module into the pipeline with the given module #
        
        Insert a module into the pipeline with the given module #. 
        'file_name' - the path to the file containing the variables for the module.
        ModuleNum - the one-based index for the placement of the module in the pipeline
        """
        module_num = new_module.module_num
        idx = module_num-1
        self.__modules = self.__modules[:idx]+[new_module]+self.__modules[idx:]
        for module,mn in zip(self.__modules[idx+1:],range(module_num+1,len(self.__modules)+1)):
            module.module_num = mn
        self.notify_listeners(ModuleAddedPipelineEvent(module_num))
    
    def remove_module(self,module_num):
        """Remove a module from the pipeline
        
        Remove a module from the pipeline
        ModuleNum - the one-based index of the module
        """
        idx =module_num-1
        module = self.__modules[idx]
        self.__modules = self.__modules[:idx]+self.__modules[idx+1:]
        module.delete()
        for module in self.__modules[idx:]:
            module.module_num = module.module_num-1
        self.notify_listeners(ModuleRemovedPipelineEvent(module_num))
    
    def test_valid(self):
        """Throw a ValidationError if the pipeline isn't valid
        
        """
        for module in self.__modules:
            module.test_valid(self)
    
    def notify_listeners(self,event):
        """Notify listeners of an event that happened to this pipeline
        
        """
        for listener in self.__listeners:
            listener(self,event)
    
    def add_listener(self,listener):
        self.__listeners.append(listener)
        
    def remove_listener(self,listener):
        self.__listeners.remove(listener)

    def is_source_loaded(self, image_name):
        """Return True if any module in the pipeline claims to be
        loading this image name from file."""
        for module in self.modules():
            if module.is_source_loaded(image_name):
                return True
        return False
    
    def get_measurement_columns(self, terminating_module=None):
        '''Return a sequence describing the measurement columns for this pipeline
        
        This call returns one element per image or object measurement
        made by each module during image set analysis. The element itself
        is a 3-tuple:
        first entry: either one of the predefined measurement categories,
                     {Image", "Experiment" or "Neighbors" or the name of one
                     of the objects.
        second entry: the measurement name (as would be used in a call 
                      to add_measurement)
        third entry: the column data type (for instance, "varchar(255)" or
                     "float")
        '''
        hash =  self.settings_hash()
        if hash != self.__measurement_column_hash:
            self.__measurement_columns = {}
            self.__measurement_column_hash = hash
        
        terminating_module_num = ((len(self.modules())+1) 
                                  if terminating_module == None
                                  else terminating_module.module_num)
        if self.__measurement_columns.has_key(terminating_module_num):
            return self.__measurement_columns[terminating_module_num]
        columns = [(cpmeas.IMAGE, IMAGE_NUMBER, cpmeas.COLTYPE_INTEGER)]
        for module in self.modules():
            if (terminating_module is not None and 
                terminating_module_num == module.module_num):
                break
            columns += module.get_measurement_columns(self)
            if module.module_name != 'ExportToDatabase':
                module_error_measurement = 'ModuleError_%02d%s'%(module.module_num,module.module_name)
                execution_time_measurement = 'ExecutionTime_%02d%s'%(module.module_num,module.module_name)
                columns += [(cpmeas.IMAGE, module_error_measurement, cpmeas.COLTYPE_INTEGER),
                            (cpmeas.IMAGE, execution_time_measurement, cpmeas.COLTYPE_INTEGER)]
        self.__measurement_columns[terminating_module_num] = columns
        return columns
    
    def synthesize_measurement_name(self, module, object, category, 
                                    feature, image, scale):
        '''Turn a measurement requested by a Matlab module into a measurement name
        
        Some Matlab modules specify measurement names as a combination
        of category, feature, image name and scale, but not all measurements
        have associated images or scales. This function attempts to match
        the given parts to the measurements available to the module and
        returns the best guess at a measurement. It throws a value error
        exception if it can't find a match
        
        module - the module requesting the measurement. Only measurements
                 made prior to this module will be considered.
        object - the object name or "Image"
        category - The module's measurement category (e.g. Intensity or AreaShape)
        feature - a descriptive name for the measurement
        image - the measurement should be made on this image (optional)
        scale - the measurement should be made at this scale
        '''
        measurement_columns = self.get_measurement_columns(module)
        measurements = [x[1] for x in measurement_columns
                        if x[0] == object]
        for measurement in ("_".join((category,feature,image,scale)),
                            "_".join((category,feature,image)),
                            "_".join((category,feature,scale)),
                            "_".join((category,feature))):
            if measurement in measurements:
                return measurement
        raise ValueError("No such measurement in pipeline: " +
                         ("Category = %s" % category) +
                         (", Feature = %s" % feature) +
                         (", Image (optional) = %s" % image) +
                         (", Scale (optional) = %s" % scale))
        
class AbstractPipelineEvent:
    """Something that happened to the pipeline and was indicated to the listeners
    """
    def event_type(self):
        raise NotImplementedError("AbstractPipelineEvent does not implement an event type")

class PipelineLoadedEvent(AbstractPipelineEvent):
    """Indicates that the pipeline has been (re)loaded
    
    """
    def event_type(self):
        return "PipelineLoaded"

class PipelineClearedEvent(AbstractPipelineEvent):
    """Indicates that all modules have been removed from the pipeline
    
    """
    def event_type(self):
        return "PipelineCleared"

DIRECTION_UP = "up"
DIRECTION_DOWN = "down"
class ModuleMovedPipelineEvent(AbstractPipelineEvent):
    """A module moved up or down
    
    """
    def __init__(self,module_num, direction):
        self.module_num = module_num
        self.direction = direction
    
    def event_type(self):
        return "Module moved"

class ModuleAddedPipelineEvent(AbstractPipelineEvent):
    """A module was added to the pipeline
    
    """
    def __init__(self,module_num):
        self.module_num = module_num
    
    def event_type(self):
        return "Module Added"
    
class ModuleRemovedPipelineEvent(AbstractPipelineEvent):
    """A module was removed from the pipeline
    
    """
    def __init__(self,module_num):
        self.module_num = module_num
        
    def event_type(self):
        return "Module deleted"

class RunExceptionEvent(AbstractPipelineEvent):
    """An exception was caught during a pipeline run
    
    """
    def __init__(self,error,module):
        self.error     = error
        self.cancel_run = True
        self.module    = module
    
    def event_type(self):
        return "Pipeline run exception"

class LoadExceptionEvent(AbstractPipelineEvent):
    """An exception was caught during pipeline loading
    
    """
    def __init__(self, error, module):
        self.error     = error
        self.cancel_run = True
        self.module    = module
    
    def event_type(self):
        return "Pipeline load exception"

def AddHandlesImages(handles,image_set):
    """Add any images from the handles to the image set
    Generally, the handles have images added as they get returned from a Matlab module.
    You can use this to update the image set and capture them.
    """
    hpipeline = handles['Pipeline'][0,0]
    pipeline_fields = hpipeline.dtype.fields.keys()
    provider_set = set([x.name for x in image_set.providers])
    image_fields = set()
    crop_fields = set()
    for field in pipeline_fields:
        if field.startswith('CropMask'):
            crop_fields.add(field)
        elif field.startswith('Segmented') or field.startswith('UneditedSegmented') or field.startswith('SmallRemovedSegmented'):
            continue
        elif field.startswith('Pathname') or field.startswith('FileList') or field.startswith('Filename'):
            if not image_set.LegacyFields.has_key(field):
                value = hpipeline[field]
                if value.dtype.kind in ['U','S']:
                    image_set.legacy_fields[field] = value[0]
                else:
                    image_set.legacy_fields[field] = value
        elif not field in provider_set:
            image_fields.add(field)
    for field in image_fields:
        image = cellprofiler.image.Image()
        image.Image = hpipeline[field]
        crop_field = 'CropMask'+field
        if crop_field in crop_fields:
            image.Mask = hpipeline[crop_field]
        image_set.providers.append(cellprofiler.image.VanillaImageProvider(field,image))
    number_of_image_sets = int(handles[CURRENT][0,0][NUMBER_OF_IMAGE_SETS][0,0])
    if (not image_set.legacy_fields.has_key(NUMBER_OF_IMAGE_SETS)) or \
           number_of_image_sets < image_set.legacy_fields[NUMBER_OF_IMAGE_SETS]:
        image_set.legacy_fields[NUMBER_OF_IMAGE_SETS] = number_of_image_sets

def add_handles_objects(handles,object_set):
    """Add any objects from the handles to the object set
    You can use this to update the object set after calling a matlab module
    """
    hpipeline = handles['Pipeline'][0,0]
    pipeline_fields = hpipeline.dtype.fields.keys()
    objects_names = set(object_set.get_object_names())
    segmented_fields = set()
    unedited_segmented_fields = set()
    small_removed_segmented_fields = set()
    for field in pipeline_fields:
        if field.startswith('Segmented'):
            segmented_fields.add(field)
        elif field.startswith('UneditedSegmented'):
            unedited_segmented_fields.add(field)
        elif field.startswith('SmallRemovedSegmented'):
            small_removed_segmented_fields.add(field)
    for field in segmented_fields:
        object_name = field.replace('Segmented','')
        if object_name in object_set.get_object_names():
            continue
        objects = cellprofiler.objects.Objects()
        objects.segmented = hpipeline[field]
        unedited_field ='Unedited'+field
        small_removed_segmented_field = 'SmallRemoved'+field 
        if unedited_field in unedited_segmented_fields:
            objects.unedited_segmented = hpipeline[unedited_field]
        if small_removed_segmented_field in small_removed_segmented_fields:
            objects.small_removed_segmented = hpipeline[small_removed_segmented_field]
        object_set.add_objects(objects,object_name)

def add_handles_measurements(handles, measurements):
    """Get measurements made by Matlab and put them into our Python measurements object
    """
    measurement_fields = handles[MEASUREMENTS].dtype.fields.keys()
    set_being_analyzed = handles[CURRENT][0,0][SET_BEING_ANALYZED][0,0]
    for field in measurement_fields:
        object_measurements = handles[MEASUREMENTS][0,0][field][0,0]
        object_fields = object_measurements.dtype.fields.keys()
        for feature in object_fields:
            if not measurements.has_current_measurements(field,feature):
                value = object_measurements[feature][0,set_being_analyzed-1]
                if not isinstance(value,numpy.ndarray) or numpy.product(value.shape) > 0:
                    # It's either not a numpy array (it's a string) or it's not the empty numpy array
                    # so add it to the measurements
                    measurements.add_measurement(field,feature,value)

debug_matlab_run = None

def debug_matlab_run(value):
    global debug_matlab_run
    debug_matlab_run = value
     
def matlab_run(handles):
    """Run a Python module, given a Matlab handles structure
    """
    if debug_matlab_run:
        import wx.py
        import wx
        class MyPyCrustApp(wx.App):
            locals = {}
            def OnInit(self):
                wx.InitAllImageHandlers()
                frame = wx.Frame(None,-1,"MatlabRun explorer")
                sizer = wx.BoxSizer()
                frame.SetSizer(sizer)
                crust = wx.py.crust.Crust(frame,-1,locals=self.locals);
                sizer.Add(crust,1,wx.EXPAND)
                frame.Fit()
                self.SetTopWindow(frame)
                frame.Show()
                return 1

    if debug_matlab_run == u"init":
        app = MyPyCrustApp(0)
        app.locals["handles"] = handles
        app.MainLoop()
        
    encapsulate_strings_in_arrays(handles)
    if debug_matlab_run == u"enc":
        app = MyPyCrustApp(0)
        app.locals["handles"] = handles
        app.MainLoop()
    orig_handles = handles
    handles = handles[0,0]
    #
    # Get all the pieces you need to run a module:
    # pipeline, image set and set list, measurements and object_set
    #
    pipeline = Pipeline()
    pipeline.create_from_handles(handles)
    image_set_list = cellprofiler.image.ImageSetList()
    image_set = image_set_list.get_image_set(0)
    measurements = cpmeas.Measurements()
    object_set = cellprofiler.objects.ObjectSet()
    #
    # Get the values for the current image_set, making believe this is the first image set
    #
    add_handles_images(handles, image_set)
    add_handles_objects(handles,object_set)
    add_handles_measurements(handles, measurements)
    current_module = int(handles[CURRENT][0,0][CURRENT_MODULE_NUMBER][0])
    #
    # Get and run the module
    #
    module = pipeline.module(current_module)
    if debug_matlab_run == u"ready":
        app = MyPyCrustApp(0)
        app.locals["handles"] = handles
        app.MainLoop()
    module.run(pipeline, image_set, object_set, measurements)
    #
    # Add everything to the handles
    #
    add_all_images(handles, image_set, object_set)
    add_all_measurements(handles, measurements)
    if debug_matlab_run == u"run":
        app = MyPyCrustApp(0)
        app.locals["handles"] = handles
        app.MainLoop()

    return orig_handles
    
if __name__ == "__main__":
    handles = scipy.io.matlab.loadmat('c:\\temp\\mh.mat',struct_as_record=True)['handles']
    handles[0,0][CURRENT][0,0][CURRENT_MODULE_NUMBER][0] = str(int(handles[0,0][CURRENT][0,0][CURRENT_MODULE_NUMBER][0])+1)
    matlab_run(handles)
