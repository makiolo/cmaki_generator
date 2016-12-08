import os
import sys
import utils
import logging
import traceback
import datetime
import hash_version
import copy
from sets import Set

class InvalidPlatform(Exception):
    def __init__(self, plat):
        self._plat = plat
    def __repr__(self):
        return "Invalid platform detected: %s" % self._plat

class DontExistsFile(Exception):
    def __init__(self, source_filename):
        self._source_filename = source_filename
    def __repr__(self):
        return 'Dont exists file %s' % self._source_filename

class FailPrepare(Exception):
    def __init__(self, node):
        self._node = node
    def __repr__(self):
        return ('Failing preparing package: %s' % self._node.get_package_name())

class AmbiguationLibs(Exception):
    def __init__(self, kind, package, build_mode):
        self._kind = kind
        self._package = package
        self._build_mode = build_mode
    def __repr__(self):
        return "Ambiguation in %s in %s. Mode: %s. Candidates:" % (self._kind, self._package, self._build_mode)

class NotFoundInDataset(Exception):
    def __init__(self, msg):
        self._msg = msg
    def __repr__(self):
        return "%s" % self._msg

class FailThirdParty(Exception):
    def __init__(self, msg):
        self._msg = msg
    def __repr__(self):
        return "%s" % self._msg

#
# INMUTABLE GLOBALS
#
HTTP_URL_NPSERVER = 'https://artifacts.000webhostapp.com/packages'
CMAKELIB_URL='https://github.com/makiolo/cmaki.git'
prefered = {}
prefered['Debug'] = ['Debug', 'RelWithDebInfo', 'Release']
prefered['RelWithDebInfo'] = ['RelWithDebInfo', 'Release', 'Debug']
prefered['Release'] = ['Release', 'RelWithDebInfo', 'Debug']
magic_invalid_file = '__not_found__'
exceptions_fail_group = (OSError, IOError, )
exceptions_fail_program = (KeyboardInterrupt, )
uncompress_strip_default = '.'
uncompress_prefix_default = '.'
priority_default = 50
build_unittests_foldername = 'unittest'
if sys.platform.startswith("win"):
    somask_id = 'w'
    archs = {'win32': '', 'win64': '64'}
    platforms = ["win32", "win64"]
elif sys.platform.startswith("linux"):  # linux2
    try:
        value = os.environ['EMSCRIPTEN']
        is_emscripten = (str(value) == '1')
    except KeyError:
        is_emscripten = False
    ######
    if is_emscripten:
        print('using emscripten ...')
        somask_id = 'e'
        archs = {'emscripten': ''}
        platforms = ["emscripten"]
    else:
        print('using linux ...')
        somask_id = 'l'
        for platform in utils.get_stdout(os.path.join('..', 'cmaki', 'ci', 'detect_operative_system.sh')):
            archs = {platform: '64'}
            platforms = [platform]
            break
elif sys.platform.startswith("sun"): # sunos5
    somask_id = 's'
    archs = {'solaris_sparc32': ''}
    platforms = ["solaris_sparc32"]
else:
    raise InvalidPlatform(sys.platform)
alias_priority_name = { 10: 'minimal',
                        20: 'tools',
                        30: 'third_party' }
alias_priority_name_inverse = {v: k for k, v in alias_priority_name.items()}


def is_valid(package_name, mask):
    return (mask.find(somask_id) != -1) and (package_name != 'dummy')

def is_blacklisted(blacklist_file, no_blacklist, package_name):
    blacklisted = False
    if os.path.exists(blacklist_file):
        with open(blacklist_file, 'rt') as f:
            for line in f.readlines():
                if line.strip() == package_name:
                    blacklisted = True
                    break
    # --no-blacklist can annular effect of blacklist
    if blacklisted and (package_name in no_blacklist):
        blacklisted = False
    return blacklisted

class ThirdParty:
    def __init__(self, user_parameters, name, parameters):
        self.user_parameters = user_parameters
        self.name = name
        self.parameters = parameters
        self.depends = []
        self.exceptions = []
        self.interrupted = False
        self.ret = 0 # Initial return code
        self.fail_stage = ""
        self.blacklisted = is_blacklisted(self.user_parameters.blacklist, self.user_parameters.no_blacklist, self.get_package_name())
        # para publicar que esta en la blacklist solo una vez
        self.published_invalidation = False

    def __hash__(self):
        return hash((self.get_package_name(), self.get_priority(), self.get_mask()))

    def __eq__(self, other):
        return (self.get_package_name() == other.get_package_name()) and (self.get_priority() == other.get_priority()) and (self.get_mask() == other.get_mask())

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "%s (%s)" % (self.get_package_name(), self.get_mask())

    def __str__(self):
        return "%s (%s)" % (self.get_package_name(), self.get_mask())

    def get_uncompress_strip(self, pos = 0):
        parms = self.parameters
        try:
            if isinstance(parms['uncompress_strip'], list):
                return parms['uncompress_strip'][pos]
            else:
                return parms['uncompress_strip']
        except KeyError:
            # default value
            return uncompress_strip_default

    def get_uncompress_prefix(self, pos = 0):
        parms = self.parameters
        try:
            if isinstance(parms['uncompress_prefix'], list):
                return parms['uncompress_prefix'][pos]
            else:
                return parms['uncompress_prefix']
        except KeyError:
            # default value
            return uncompress_prefix_default

    def get_uncompress(self, pos = 0):
        parms = self.parameters
        try:
            if parms['uncompress'] is not None:
                if isinstance(parms['uncompress'], list):
                    return (parms['uncompress'][pos].find(somask_id) != -1)
                else:
                    return (parms['uncompress'].find(somask_id) != -1)
            else:
                return False
        except KeyError:
            # default value
            return True

    def get_depends_raw(self):
        return self.depends

    def get_depends(self):
        parms = self.parameters
        try:
            return parms['depends']
        except KeyError:
            # default value
            return None

    def get_generate_custom_script(self, source_dir):
        path_build = self.get_path_custom_script(source_dir, name='.build')
        build_content = self.get_build_script_content()
        if build_content is not None:
            with open(path_build, 'wt') as f:
                f.write(build_content)

    def get_path_custom_script(self, source_folder, name = 'build'):
        if utils.is_windows():
            path_build = os.path.join(source_folder, name + '.cmd')
        else:
            path_build = os.path.join(source_folder, name + '.sh')
        return path_build

    def has_custom_script(self, source_folder):
        script_custom = os.path.exists( self.get_path_custom_script(source_folder) )
        return (self.get_build_script_content() is not None) or script_custom

    def get_build_script_content(self):
        parms = self.parameters
        try:
            return parms['build']
        except KeyError:
            # default value
            return None

    def get_source(self):
        parms = self.parameters
        try:
            source = parms['source']
            if source is not None:
                if not isinstance(source, list):
                    return [source]
                else:
                    return source
            else:
                return []
        except KeyError:
            # default value
            return []

    def get_source_filename(self, position=0):
        parms = self.parameters
        try:
            return parms['source_filename']
        except KeyError:
            # default value
            source = self.get_source()[position]
            filename = source.split('/')[-1]
            return filename

    def get_sources_all(self, position=0):
        parms = self.parameters
        try:
            return parms['sources_all']
        except KeyError:
            return False

    def get_before_copy(self):
        parms = self.parameters
        try:
            return parms['before_copy']
        except KeyError:
            # default value
            return []

    def get_short_path(self):
        parms = self.parameters
        try:
            return parms['short_path']
        except KeyError:
            # default value
            return False

    def has_library(self, platform_info):
        package = self.get_package_name()
        return ((('static' in platform_info) and (package != 'dummy')) or (('dynamic' in platform_info) and (package != 'dummy')))

    def needs(self, node):
        if node.is_valid():
            self.depends.append(node)

    def get_package_name(self):
        return self.name

    def get_package_name_norm(self):
        package = self.get_package_name()
        for c in '-\\/:*?"<>|':
            package = package.replace(c, '_')
        return package

    def get_package_name_norm_upper(self):
        package_norm = self.get_package_name_norm()
        return package_norm.upper()

    def set_version(self, newversion):
        self.parameters['version'] = newversion

    def get_version(self):
        parms = self.parameters
        try:
            return parms['version']
        except KeyError:
            if self.get_package_name() != 'dummy':
                raise Exception('[%s] Version is a mandatory field.' % self.get_package_name())

    def get_version_manager(self):
        parms = self.parameters
        try:
            return parms['version_manager']
        except KeyError:
            return None

    def get_cmake_target(self):
        parms = self.parameters
        try:
            return parms['cmake_target']
        except KeyError:
            return 'install'

    def get_post_install(self):
        parms = self.parameters
        try:
            return parms['post_install']
        except KeyError:
            return []

    def get_priority(self):
        parms = self.parameters
        try:
            return int(parms['priority'])
        except KeyError:
            return priority_default

    def has_version_compatible(self):
        return 'version_compatible' in self.parameters

    def get_version_compatible(self):
        parms = self.parameters
        try:
            # comvert X in x
            return str(parms['version_compatible']).lower()
        except KeyError:
            # default value
            return self.get_version()

    def is_packing(self):
        parms = self.parameters
        try:
            return parms['packing']
        except KeyError:
            # default value
            return True

    def get_branch(self):
        try:
            return self.parameters['branch']
        except KeyError:
            # default value
            return None

    def get_build_modes(self):
        parms = self.parameters
        build_modes = []
        try:
            mode = parms['mode']
            if mode.find('d') != -1:
                build_modes.append('Debug')
            if mode.find('i') != -1:
                build_modes.append('RelWithDebInfo')
            if mode.find('r') != -1:
                build_modes.append('Release')
        except KeyError:
            # no mode provided
            build_modes.append('Debug')
            build_modes.append('RelWithDebInfo')
            build_modes.append('Release')
        return build_modes

    def get_mask(self):
        parms = self.parameters
        try:
            return parms['mask']
        except KeyError:
            return somask_id

    def is_valid(self):
        if self.blacklisted:
            if (not self.published_invalidation):
                logging.debug('%s is not built because is blacklisted in %s' % (self.get_package_name(), os.path.basename(self.user_parameters.blacklist)))
                self.published_invalidation = True
            return False
        return is_valid(self.get_package_name(), self.get_mask())

    def resolver(self, resolved, seen):
        seen.append(self)
        for edge in self.depends:
            if edge not in resolved:
                if edge in seen:
                    raise Exception('Circular reference detected: %s and %s' % (self.get_package_name(), edge.name))
                edge.resolver(resolved, seen)
        if self.is_valid():
            resolved.append(self)
        seen.remove(self)

    def get_targets(self):
        try:
            return self.parameters['targets']
        except KeyError:
            # default value
            return []

    def get_exclude_from_all(self):
        parms = self.parameters
        try:
            return parms['exclude_from_all']
        except KeyError:
            # default value
            return False

    def get_exclude_from_clean(self):
        parms = self.parameters
        try:
            return parms['exclude_from_clean']
        except KeyError:
            # default value
            return False

    def get_install(self):
        parms = self.parameters
        try:
            return parms['install']
        except KeyError:
            # default value
            return True

    def is_toolchain(self):
        parms = self.parameters
        try:
            return parms['is_toolchain']
        except KeyError:
            # default value
            return False

    def get_unittest(self):
        parms = self.parameters
        try:
            return parms['unittest']
        except KeyError:
            # default value
            return None

    def get_cmake_prefix(self):
        parms = self.parameters
        try:
            cmake_prefix = parms['cmake_prefix']
            if cmake_prefix.endswith('CMakeLists.txt'):
                return os.path.dirname(cmake_prefix)
            return cmake_prefix
        except KeyError:
            # default value
            return "."

    def get_generator_targets(self, plat, compiler_c, compiler_cpp, ext_sta, ext_dyn):
        '''
        TODO: create new class "target"
        '''

        superpackage = self.get_package_name_norm()

        for targets in self.get_targets():

            for target_name in targets:

                target_info = targets[target_name]

                # info is mandatory for each platform
                # extra os optional
                if 'info' in target_info:
                    outputinfo = target_info['info']
                    if plat in outputinfo:
                        platform_info = copy.deepcopy( outputinfo[plat] )
                    elif 'default' in outputinfo:
                        platform_info = copy.deepcopy( outputinfo['default'] )
                    else:
                        platform_info = None
                else:
                    platform_info = None

                if 'extra' in target_info:
                    outputinfo_extra = target_info['extra']
                    if plat in outputinfo_extra:
                        platform_extra = copy.deepcopy( outputinfo_extra[plat] )
                    elif 'default' in outputinfo_extra:
                        platform_extra = copy.deepcopy( outputinfo_extra['default'] )
                    else:
                        platform_extra = None
                else:
                    platform_extra = None

                if (platform_info is not None) and (platform_extra is not None):
                    platform_info = utils.smart_merge(platform_info, platform_extra)

                # variables for use in "info" and "extra"
                platform_info = utils.apply_replaces_vars(platform_info, {
                                                                            'TARGET': target_name,
                                                                            'TARGET_UPPER': target_name.upper(),
                                                                            'PACKAGE': superpackage,
                                                                            'PACKAGE_UPPER': superpackage.upper(),
                                                                            'PLATFORM': plat,
                                                                            'COMPILER': os.path.basename(compiler_cpp),
                                                                            'EXT_DYN': ext_dyn,
                                                                            'EXT_STA': ext_sta,
                                                                            'ARCH': archs[plat],
                                                                        })

                if platform_info is None:
                    logging.error('No platform info in package %s, platform %s' % (superpackage, plat))
                    logging.error("%s" % targets)
                    sys.exit(1)

                yield (target_name, platform_info)

    # true if have any static target
    def have_any_in_target(self, plat, key, compiler_replace_maps):
        any_static = False
        for compiler_c, compiler_cpp, _, ext_sta, ext_dyn, _, _ in self.compiler_iterator(plat, compiler_replace_maps):
            for package, platform_info in self.get_generator_targets(plat, compiler_c, compiler_cpp, ext_sta, ext_dyn):
                if key in platform_info:
                    any_static = True
        return any_static

    def get_generate_find_package(self):
        parms = self.parameters
        try:
            return parms['generate_find_package']
        except KeyError:
            # default value
            return True

    def compiler_iterator(self, plat, compiler_replace_maps):
        parameters = self.parameters
        generator = None
        compilers = None
        class Found(Exception): pass
        try:
            for key in parameters['platforms']:
                if key == plat:
                    plat_parms = parameters['platforms'][key]
                    raise Found()
            else:
                if 'default' in parameters['platforms']:
                    plat_parms = parameters['platforms']['default']
                    raise Found()
                else:
                    raise Exception("not found 'default' platform or %s" % plat)
        except Found:
            try:
                generator = plat_parms['generator']
            except KeyError:
                generator = None

            try:
                compilers = plat_parms['compiler']
            except KeyError:
                compilers = None

        # resolve map
        compiler_replace_resolved = {}
        for var, value in compiler_replace_maps.iteritems():
            newvalue = value
            newvalue = newvalue.replace('$PLATFORM', plat)
            compiler_replace_resolved[var] = newvalue
        compiler_replace_resolved['$ARCH'] = archs[plat]
        compiler_replace_resolved['${ARCH}'] = archs[plat]

        ext_dyn = plat_parms['ext_dyn']
        ext_sta = plat_parms['ext_sta']
        if compilers is None:
            compilers = [('%s, %s' % (os.environ.get('CC', 'gcc'), os.environ.get('CXX', 'g++')))]

        for compiler in compilers:
            compilers_tuple = compiler.split(',')
            assert(len(compilers_tuple) == 2)
            compiler_c = compilers_tuple[0].strip()
            compiler_cpp = compilers_tuple[1].strip()

            compiler_c = utils.apply_replaces(compiler_c, compiler_replace_resolved)
            compiler_cpp = utils.apply_replaces(compiler_cpp, compiler_replace_resolved)

            env_new = {}
            env_modified = os.environ.copy()

            for env_iter in [env_modified, env_new]:

                basename_compiler_cpp = os.path.basename(compiler_cpp)
                env_iter['COMPILER'] = str(basename_compiler_cpp)
                env_iter['PLATFORM'] = str(plat)
                env_iter['PACKAGE'] = str(self.get_package_name())
                env_iter['VERSION'] = str(self.get_version())
                env_iter['ARCH'] = str(archs[plat])

                if (compiler_c != 'default') and (compiler_cpp != 'default'):
                    env_iter['CC'] = str(compiler_c)
                    env_iter['CXX'] = str(compiler_cpp)

                try:
                    environment = plat_parms['environment']

                    try:
                        environment_remove = environment['remove']
                        for key, values in  environment_remove.iteritems():
                            try:
                                oldpath = env_iter[key]
                            except KeyError:
                                oldpath = ''
                            uniq_values = Set()
                            for v in values:
                                v = utils.apply_replaces(v, compiler_replace_resolved)
                                uniq_values.add(v)
                            for v in uniq_values:
                                oldpath = oldpath.replace(v, '')
                            env_iter[key] = oldpath
                    except KeyError:
                        pass

                    # insert front with seprator = ":"
                    try:
                        environment_push_front = environment['push_front']
                        for key, values in  environment_push_front.iteritems():
                            try:
                                oldpath = env_iter[key]
                            except KeyError:
                                oldpath = ''
                            uniq_values = Set()
                            for v in values:
                                v = utils.apply_replaces(v, compiler_replace_resolved)
                                uniq_values.add(v)
                            for v in uniq_values:
                                if len(oldpath) == 0:
                                    separator = ''
                                else:
                                    # -L / -I / -R use space
                                    if v.startswith('-'):
                                        separator = ' '
                                    else:
                                        separator = ':'
                                oldpath = str('%s%s%s' % (v, separator, oldpath))
                            env_iter[key] = oldpath
                    except KeyError:
                        pass

                    # insert back with separator " "
                    try:
                        environment_flags = environment['flags']
                        for key, values in  environment_flags.iteritems():
                            try:
                                oldpath = env_iter[key]
                            except KeyError:
                                oldpath = ''
                            uniq_values = Set()
                            for v in values:
                                v = utils.apply_replaces(v, compiler_replace_resolved)
                                uniq_values.add(v)
                            for v in uniq_values:
                                if len(oldpath) == 0:
                                    separator = ''
                                else:
                                    separator = ' '
                                oldpath = str('%s%s%s' % (oldpath, separator, v))
                            env_iter[key] = oldpath
                    except KeyError:
                        pass

                    # insert new environment variables
                    try:
                        environment_assign = environment['assign']
                        for key, value in  environment_assign.iteritems():
                            value = utils.apply_replaces(value, compiler_replace_resolved)
                            env_iter[key] = value
                    except KeyError:
                        pass

                except KeyError:
                    pass

            yield (compiler_c, compiler_cpp, generator, ext_sta, ext_dyn, env_modified, env_new)

    def remove_cmake3p(self, cmake3p_dir):
        package_cmake3p = os.path.join(cmake3p_dir, self.get_base_folder())
        logging.debug('Removing cmake3p %s' % package_cmake3p)
        if os.path.exists(package_cmake3p):
            utils.tryremove_dir(package_cmake3p)
        for dep in self.get_depends_raw():
            dep.remove_cmake3p(cmake3p_dir)

    def get_base_folder(self):
        package = self.get_package_name()
        version = self.get_version()
        return '%s-%s' % (package, version)

    def get_workspace(self, plat):
        package = self.get_package_name()
        version = self.get_version()
        return '%s-%s-%s' % (package, version, plat)

    def get_build_directory(self, plat, build_mode):
        package = self.get_package_name()
        version = self.get_version()
        if not self.get_short_path():
            return '.build_%s-%s-%s_%s' % (package, version, plat, build_mode)
        else:
            return '.bs_%s%s%s%s' % (package[:3], version[-1:], plat, build_mode)

    def get_download_directory(self):
        package = self.get_package_name()
        return '.download_%s' % package

    def get_original_directory(self):
        package = self.get_package_name()
        return '.download_original_%s' % package

    def apply_replace_maps(self, compiler_replace_maps):
        package = self.get_package_name()
        package_norm = self.get_package_name_norm()
        to_package = os.path.abspath(package)
        utils.trymkdir(to_package)
        with utils.working_directory(to_package):
            basedir = os.path.abspath('..')
            if not self.is_toolchain():
                compiler_replace_maps['$%s_BASE' % package_norm] = os.path.join(basedir, self.get_workspace('$PLATFORM'), self.get_base_folder())
            else:
                compiler_replace_maps['$%s_BASE' % package_norm] = self.user_parameters.toolchain

    def generate_scripts_headers(self, compiler_replace_maps):
        package = self.get_package_name()
        package_norm = self.get_package_name_norm()
        version = self.get_version()
        to_package = os.path.abspath(package)
        utils.trymkdir(to_package)
        with utils.working_directory(to_package):
            basedir = os.path.abspath('..')

            if not self.is_toolchain():

                # generate find.cmake
                build_directory = self.get_build_directory(r"${GLOBAL_PLATFORM}", r"${GLOBAL_BUILD_MODE}")
                with open('find.cmake', 'wt') as f:
                    f.write("SET(%s_VERSION %s CACHE STRING \"Last version compiled ${PACKAGE}\" FORCE)\n" % (package_norm, version))
                    f.write("file(TO_NATIVE_PATH \"${PACKAGE_BUILD_DIRECTORY}/../%s-%s-${GLOBAL_PLATFORM}/%s-%s/include\" %s_INCLUDE)\n" % (package, version, package, version, package_norm))
                    f.write("file(TO_NATIVE_PATH \"${PACKAGE_BUILD_DIRECTORY}/../%s-%s-${GLOBAL_PLATFORM}/%s-%s/${GLOBAL_PLATFORM}/${GLOBAL_COMPILER}/${GLOBAL_BUILD_MODE}\" %s_LIBDIR)\n" % (package, version, package, version, package_norm))
                    f.write("file(TO_NATIVE_PATH \"${PACKAGE_BUILD_DIRECTORY}/../%s\" %s_BUILD)\n" % (build_directory, package_norm))
                    f.write("SET(%s_INCLUDE ${%s_INCLUDE} CACHE STRING \"Include dir %s\" FORCE)\n" % (package_norm, package_norm, package))
                    f.write("SET(%s_LIBDIR ${%s_LIBDIR} CACHE STRING \"Libs dir %s\" FORCE)\n" % (package_norm, package_norm, package))
                    f.write("SET(%s_BUILD ${%s_BUILD} CACHE STRING \"Build dir %s\" FORCE)\n" % (package_norm, package_norm, package))

                # genereate find.script / cmd
                if utils.is_windows():
                    build_directory = self.get_build_directory("%PLATFORM%", "%BUILD_MODE%")
                    with open('find.cmd', 'wt') as f:
                        f.write("set %s_VERSION=%s\n" % (package_norm, version))
                        f.write("set %s_HOME=%s\%s-%s-%%PLATFORM%%\%s-%s\%%PLATFORM%%\%%COMPILER%%\%%BUILD_MODE%%\n" % (package_norm, basedir, package, version, package, version))
                        f.write("set %s_BASE=%s\%s-%s-%%PLATFORM%%\%s-%s\n" % (package_norm, basedir, package, version, package, version))
                        f.write("set SELFHOME=%s\%%PACKAGE%%-%%VERSION%%-%%PLATFORM%%\%%PACKAGE%%-%%VERSION%%\%%PLATFORM%%\%%COMPILER%%\%%BUILD_MODE%%\n" % (basedir))
                        f.write("set SELFBASE=%s\%%PACKAGE%%-%%VERSION%%-%%PLATFORM%%\%%PACKAGE%%-%%VERSION%%\n" % (basedir))
                        f.write("set %s_BUILD=%s\%s\n" % (package_norm, basedir, build_directory))
                        f.write(r"md %SELFHOME%")
                        f.write("\n")
                else:
                    build_directory = self.get_build_directory("${PLATFORM}", "${BUILD_MODE}")
                    with open('find.script', 'wt') as f:
                        f.write("#!/bin/bash\n")
                        f.write("%s_VERSION=%s\n" % (package_norm, version))
                        f.write("%s_HOME=%s/%s-%s-$PLATFORM/%s-%s/$PLATFORM/$COMPILER/$BUILD_MODE\n" % (package_norm, basedir, package, version, package, version))
                        f.write("%s_BASE=%s/%s-%s-$PLATFORM/%s-%s\n" % (package_norm, basedir, package, version, package, version))
                        f.write("SELFHOME=%s/$PACKAGE-$VERSION-$PLATFORM/$PACKAGE-$VERSION/$PLATFORM/$COMPILER/$BUILD_MODE\n" % (basedir))
                        f.write("SELFBASE=%s/$PACKAGE-$VERSION-$PLATFORM/$PACKAGE-$VERSION\n" % (basedir))
                        f.write("%s_BUILD=%s/%s\n" % (package_norm, basedir, build_directory))
                        f.write("mkdir -p $SELFHOME\n")
            else:
                if utils.is_windows():
                    logging.debug('ERROR: Windows dont have toolchain.')
                else:
                    with open('find.script', 'wt') as f:
                        f.write("#!/bin/bash\n")
                        f.write("%s_VERSION=%s\n" % (package_norm, version))
                        f.write("%s_HOME=%s\n" % (package_norm, self.user_parameters.toolchain))
                        f.write("%s_BASE=%s\n" % (package_norm, self.user_parameters.toolchain))
                        f.write("SELFHOME=%s\n" % (self.user_parameters.toolchain))
                        f.write("SELFBASE=%s\n" % (self.user_parameters.toolchain))
                        f.write("mkdir -p $SELFHOME\n")

    def remove_cmakefiles(self):
        utils.tryremove('CMakeCache.txt')
        utils.tryremove('cmake_install.cmake')
        utils.tryremove('install_manifest.txt')
        utils.tryremove_dir('CMakeFiles')


    def remove_scripts_headers(self):
        package = self.get_package_name()
        to_package = os.path.abspath(package)
        utils.trymkdir(to_package)
        with utils.working_directory(to_package):
            utils.tryremove('find.cmake')
            utils.tryremove('find.script')
            utils.tryremove('find.cmd')
            utils.tryremove('.build.sh')
            utils.tryremove('.build.cmd')
        utils.tryremove_dir_empty(to_package)

    def generate_3rdpartyversion(self, output_dir):
        package = self.get_package_name()
        package_norm_upper = self.get_package_name_norm_upper()
        version = self.get_version()
        packing = self.is_packing()
        if not packing:
            logging.debug("package %s, don't need 3rdpartyversion" % package)
            return
        thirdparty_path = os.path.join(output_dir, '3rdpartyversions')
        utils.trymkdir(thirdparty_path)
        with utils.working_directory(thirdparty_path):
            with open('%s.cmake' % package, 'wt') as f:
                if not self.has_version_compatible():
                    f.write('SET(%s_REQUIRED_VERSION %s EXACT)\n' % (package_norm_upper, version))
                else:
                    f.write('SET(%s_REQUIRED_VERSION %s)\n' % (package_norm_upper, version))

    def _smart_uncompress(self, position, package_file_abs, uncompress_directory, destiny_directory, compiler_replace_maps):
        uncompress = self.get_uncompress(position)
        uncompress_strip = self.get_uncompress_strip(position)
        uncompress_prefix = self.get_uncompress_prefix(position)
        if uncompress:
            if (uncompress_strip == uncompress_strip_default) and (uncompress_prefix == uncompress_prefix_default):
                # case fast (don't need intermediate folder)
                ok = utils.extract_file(package_file_abs, destiny_directory, self.get_first_environment(compiler_replace_maps))
            else:
                source_with_strip = os.path.join(uncompress_directory, uncompress_strip)
                destiny_with_prefix = os.path.join(destiny_directory, uncompress_prefix)
                ok = utils.extract_file(package_file_abs, uncompress_directory, self.get_first_environment(compiler_replace_maps))
                utils.move_folder_recursive(source_with_strip, destiny_with_prefix)
                utils.tryremove_dir(source_with_strip)
            if not ok:
                raise Exception('Invalid uncompressed package %s - %s' % (package, package_file_abs))

    def _prepare_third_party(self, position, url, build_directory, compiler_replace_maps):
        package = self.get_package_name()
        source_filename = self.get_source_filename(position)
        uncompress_strip = self.get_uncompress_strip(position)
        uncompress_prefix = self.get_uncompress_prefix(position)
        uncompress = self.get_uncompress(position)
        uncompress_directory = self.get_download_directory()
        utils.trymkdir(uncompress_directory)

        logging.debug('source_filename = %s' % source_filename)
        logging.debug('uncompress_strip = %s' % uncompress_strip)
        logging.debug('uncompress_prefix = %s' % uncompress_prefix)
        logging.debug('uncompress = %s' % uncompress)

        # resolve url vars
        url = url.replace('$HTTP_URL_NPSERVER', HTTP_URL_NPSERVER)

        # files in svn
        if(url.startswith('svn://')):
            # strip is not implemmented with svn://
            utils.tryremove_dir( build_directory )
            logging.info('Download from svn: %s' % url)
            self.safe_system( 'svn co %s %s' % (url, build_directory), compiler_replace_maps )
            # utils.tryremove_dir( os.path.join(build_directory, '.svn') )

        elif(url.endswith('.git') or (url.find('github') != -1) or (url.find('bitbucket') != -1)):
            # strip is not implemmented with git://
            utils.tryremove_dir( build_directory )
            logging.info('Download from git: %s' % url)
            branch = self.get_branch()
            extra_cmd = ''
            if branch is not None:
                logging.info('clonning to branch %s' % branch)
                extra_cmd = '-b %s' % branch
            self.safe_system('git clone %s --recursive %s %s' % (extra_cmd, url, build_directory), compiler_replace_maps)
            depends_file = self.user_parameters.depends
            if depends_file is not None:
                with utils.working_directory(build_directory):
                    # leer el fichero de dependencias
                    if os.path.exists(depends_file):
                        data = utils.deserialize(depends_file)
                    else:
                        data = {}

                    # obedecer, si trae algo util
                    if package in data:
                        logging.debug('data package version is %s' % data[package])
                        try:
                            git_version = hash_version.to_git_version(build_directory, data[package])
                            logging.debug('data package in git version is %s' % git_version)
                            logging.debug('updating to revision %s' % git_version)
                            self.safe_system('git reset --hard %s' % git_version, compiler_replace_maps)
                        except AssertionError:
                            logging.info('using HEAD')

                    # actualizar y reescribir
                    revision = hash_version.get_last_version(build_directory)
                    assert(len(revision) > 0)
                    data[package] = revision
                    utils.serialize(data, depends_file)
            else:
                logging.warning('not found depends file, using newest changeset')

        # file in http
        elif (     url.startswith('http://')
                or url.startswith('https://')
                or url.endswith('.zip')
                or url.endswith('.tar.gz')
                or url.endswith('.tar.bz2')
                or url.endswith('.tgz')
                or url.endswith('.py') ):

            logging.info('Download from url: %s' % url)
            # download to source_filename
            package_file_abs = os.path.join(uncompress_directory, source_filename)
            utils.download_from_url(url, package_file_abs)
            if os.path.isfile(package_file_abs):

                # uncompress in download folder for after generate a patch with all changes
                if not os.path.isdir( self.get_original_directory() ):
                    utils.trymkdir( self.get_original_directory() )
                    logging.debug('preparing original uncompress')
                    # uncompress in original
                    self._smart_uncompress(position, package_file_abs, uncompress_directory, self.get_original_directory(), compiler_replace_maps)
                else:
                    logging.debug('skipping original uncompress (already exists)')

                # uncompress in intermediate build directory
                self._smart_uncompress(position, package_file_abs, uncompress_directory, build_directory, compiler_replace_maps)

            else:
                raise DontExistsFile(source_filename)

        else:
            raise Exception('Invalid source: %s - %s' % (package, url))

    def prepare_third_party(self, build_directory, compiler_replace_maps):
        utils.trymkdir(build_directory)
        package = self.get_package_name()
        version = self.get_version()
        sources_all = self.get_sources_all()
        exceptions = []
        i = 0
        for source_url in self.get_source():
            if (source_url is None) or (len(source_url) <= 0) or (source_url == 'skip'):
                logging.warning('[%s %s] Skipping preparation ...' % (package, version))
            else:
                logging.warning('[%s %s] trying prepare from %s ...' % (package, version, source_url))
                try:
                    self._prepare_third_party(i, source_url, build_directory, compiler_replace_maps)
                    if not sources_all:
                        # sources_all = false ---> any source
                        # sources_all = Trie ----> all source
                        break
                except exceptions_fail_group + exceptions_fail_program:
                    raise
                except:
                    exceptions.append(sys.exc_info())
            i += 1
        if len(exceptions) > 0:
            i = 0
            for exc_type, exc_value, exc_traceback in exceptions:
                print "---- Exception #%d / %d ----------" % (i+1, len(exceptions))
                traceback.print_exception(exc_type, exc_value, exc_traceback)
                print "----------------------------------"
                i += 1
            raise FailPrepare(self)

    def get_prefered_build_mode(self, prefered_build_mode_list):
        build_modes = self.get_build_modes()
        assert(len(prefered_build_mode_list) > 0)
        prefered_build_mode = prefered_build_mode_list[0]
        while (prefered_build_mode not in build_modes) and (len(prefered_build_mode_list)>0):
            prefered_build_mode_list.pop(0)
            if len(prefered_build_mode_list) > 0:
                prefered_build_mode = prefered_build_mode_list[0]
        return prefered_build_mode

    def generate_cmake_condition(self, platforms, compiler_replace_maps):
        target_uniques = Set()
        condition = ''
        i = 0
        for plat in platforms:
            for compiler_c, compiler_cpp, _, ext_sta, ext_dyn, _, _ in self.compiler_iterator(plat, compiler_replace_maps):
                for package, platform_info in self.get_generator_targets(plat, compiler_c, compiler_cpp, ext_sta, ext_dyn):
                    package_lower = package.lower()
                    if (package_lower not in target_uniques) and (package_lower != 'dummy'):
                        target_uniques.add(package_lower)
                        if self.has_library(platform_info):
                            if i == 0:
                                condition += '(NOT TARGET %s)' % package_lower
                            else:
                                condition += ' OR (NOT TARGET %s)' % package_lower
                        i += 1
        return condition

    def _get_lib(self, rootdir, file_dll, build_mode):
        '''
        3 cases:
            string
            pattern as special string
            list of strings
        '''
        if file_dll is None:
            logging.warning('Failed searching lib in %s' % rootdir)
            return (False, None)

        package = self.get_package_name()
        if isinstance(file_dll, list):
            utils.verbose(self.user_parameters, 'Searching list %s' % file_dll)
            valid_ff = None
            for ff in file_dll:
                valid, valid_ff = self._get_lib(rootdir, utils.get_norm_path(ff), build_mode)
                if valid:
                    break
            return (valid, valid_ff)

        elif file_dll.startswith('/') and file_dll.endswith('/'):
            pattern = file_dll[1:-1]
            utils.verbose(self.user_parameters, 'Searching rootdir %s, pattern %s' % (rootdir, pattern))
            files_found = utils.rec_glob(rootdir, pattern, deep_max=10)
            utils.verbose(self.user_parameters, 'Candidates %s' % files_found)
            if len(files_found) == 1:
                relfile = os.path.relpath(files_found[0], rootdir)
                return (True, utils.get_norm_path(relfile))
            elif len(files_found) == 0:
                msg = 'No library found in %s with pattern %s' % (rootdir, pattern)
                logging.debug(msg)
                return (False, None)
            else:
                msg = "Ambiguation in %s. Mode: %s. Candidates:" % (package, build_mode)
                logging.debug(msg)
                return (False, None)
        else:
            pathfull = os.path.join(rootdir, file_dll)
            utils.verbose(self.user_parameters, 'Checking file %s' % pathfull)
            if os.path.exists(pathfull):
                return (True, utils.get_norm_path(file_dll))
            else:
                return (False, None)

    def get_lib(self, workbase, dataset, build_mode, kind, rootdir=None):
        '''
        Can throw exception
        '''
        package = self.get_package_name()
        if rootdir is None:
            rootdir = os.path.join(workbase, build_mode)
        utils.verbose(self.user_parameters, 'Searching rootdir %s' % (rootdir))
        if (build_mode.lower() in dataset) and (kind in dataset[build_mode.lower()]):
            file_dll = dataset[build_mode.lower()][kind]
            valid, valid_ff = self._get_lib(rootdir, file_dll, build_mode)
            if valid:
                return valid_ff
            else:
                raise AmbiguationLibs(kind, package, build_mode)
        else:
            raise NotFoundInDataset("Not found in dataset, searching %s - %s" % (build_mode.lower(), kind))

    def get_lib_basename(self, workbase, dataset, build_mode, kind, base=False):
        '''
        First search in build mode specific
        Second search in BASE
        Other case return __not_found__.$kind
        '''
        try:
            build_mode = self.get_prefered_build_mode(prefered[build_mode])
            try:
                if not base:
                    finalpath = os.path.join(build_mode, self.get_lib(workbase, dataset, build_mode, kind))
                    utils.superverbose(self.user_parameters, '[01] path: %s' % finalpath)
                    return finalpath
                else:
                    # undo platform and compiler
                    # search in base
                    rootdir = os.path.abspath(os.path.join(workbase, '..' , '..'))
                    finalpath = os.path.join('..', '..', self.get_lib(workbase, dataset, build_mode, kind, rootdir))
                    utils.superverbose(self.user_parameters, '[02] path: %s' % finalpath)
                    return finalpath

            except AmbiguationLibs:
                # try search in BASE
                if (not base):
                    finalpath = self.get_lib_basename(workbase, dataset, build_mode, kind, base=True)
                    utils.superverbose(self.user_parameters, '[03] path: %s' % finalpath)
                    return finalpath
                else:
                    finalpath = os.path.join(build_mode, ('%s.%s' % (magic_invalid_file, kind)))
                    utils.superverbose(self.user_parameters, '[04] path: %s' % finalpath)
                    return finalpath
        except NotFoundInDataset:
            # exception -> return invalid file
            finalpath = os.path.join(build_mode, ('%s.%s' % (magic_invalid_file, kind)))
            utils.superverbose(self.user_parameters, '[05] path: %s' % finalpath)
            return finalpath

    def check_libs_exists(self, workbase, superpackage, package, dataset, kindlibs, build_modes=None):
        all_ok = True
        if build_modes is None:
            build_modes = self.get_build_modes()
        for build_mode in build_modes:
            for kind, must in kindlibs:
                try:
                    file_dll = self.get_lib_basename(workbase, dataset, build_mode, kind)
                    dll_path = os.path.join(workbase, file_dll)
                    if not os.path.exists(dll_path):
                        if must:
                            logging.error("[%s] Don't found %s in %s. Mode: %s. Path: %s" % (superpackage, kind, package, build_mode, dll_path))
                            all_ok = False
                        else:
                            msg = "[%s] Don't found %s in %s. Mode: %s. Path: %s" % (superpackage, kind, package, build_mode, dll_path)
                            if build_mode != 'Release':
                                logging.warning(msg)
                            else:
                                logging.debug(msg)
                except NotFoundInDataset as e:
                    if must:
                        logging.error("[ERROR] [NOT FOUND] [%s] %s" % (superpackage, e))
                        all_ok = False
        return all_ok

    def is_invalid_lib(self, libpath):
        return (libpath is None) or (utils.get_filename_no_ext(os.path.basename(libpath)) == magic_invalid_file)

    def generate_cmakefiles(self, platforms, folder_output, compiler_replace_maps):
        errors = 0
        packing = self.is_packing()
        if not packing:
            logging.warning("package: %s don't need generate cmakefiles" % self.get_package_name())
            return errors
        oldcwd = os.getcwd()
        utils.trymkdir(folder_output)
        with utils.working_directory(folder_output):
            superpackage = self.get_package_name()
            superpackage_lower = superpackage.lower()
            superpackage_upper = superpackage.upper()
            build_modes = self.get_build_modes()
            parameters = self.parameters
            version_compatible = self.get_version_compatible()

            for plat in platforms:
                for compiler_c, compiler_cpp, _, ext_sta, ext_dyn, _, _ in self.compiler_iterator(plat, compiler_replace_maps):
                    workspace = self.get_workspace(plat)
                    base_folder = self.get_base_folder()
                    if 'common_factor' in parameters:
                        common_factor = parameters['common_factor']
                        prefered_build_mode = self.get_prefered_build_mode(prefered['Release'])
                        for d in common_factor:
                            for build_mode in build_modes:
                                basename_compiler_cpp = os.path.basename(compiler_cpp)
                                build_depend_folder = os.path.join(oldcwd, workspace, base_folder, plat, basename_compiler_cpp, build_mode, d)
                                if build_mode == prefered_build_mode:
                                    # Move from prefered build mode (release) to common folder
                                    common_folder = os.path.join(oldcwd, workspace, base_folder, d)
                                    if os.path.exists(build_depend_folder):
                                        utils.copy_folder_recursive(build_depend_folder, common_folder)
                                utils.tryremove_dir(build_depend_folder)

            with open('%s-config.cmake' % superpackage_lower, 'wt') as f:
                f.write('''CMAKE_POLICY(PUSH)
CMAKE_POLICY(VERSION 2.8)
cmake_minimum_required(VERSION 2.8)
cmake_policy(SET CMP0011 NEW)
                ''')

                condition = self.generate_cmake_condition(platforms, compiler_replace_maps)
                if(len(condition) > 0):
                    f.write('\nif(%s)\n' % condition)

                f.write('''\ninclude(${CMAKI_PATH}/facts/facts.cmake)
cmaki_download_package()
file(TO_NATIVE_PATH "${_DIR}" %s_HOME)
file(TO_NATIVE_PATH "${_DIR}/${CMAKI_PLATFORM}" %s_PREFIX)
set(%s_HOME "${%s_HOME}" PARENT_SCOPE)
set(%s_PREFIX "${%s_PREFIX}" PARENT_SCOPE)
include(${_MY_DIR}/${CMAKI_PLATFORM}.cmake)
                ''' % (superpackage_upper, superpackage_upper, superpackage_upper, superpackage_upper, superpackage_upper, superpackage_upper))

                if(len(condition) > 0):
                    f.write('\nendif()\n')

                f.write('\nCMAKE_POLICY(POP)')

            with open('%s-config-version.cmake' % superpackage_lower, 'wt') as f:
                f.write('''\
cmake_minimum_required(VERSION 2.8)
cmake_policy(SET CMP0011 NEW)

include(${CMAKI_PATH}/facts/facts.cmake)
cmaki_package_version_check()
                ''')

            for plat in platforms:

                workspace = self.get_workspace(plat)
                base_folder = self.get_base_folder()

                for compiler_c, compiler_cpp, _, ext_sta, ext_dyn, env_modified, _ in self.compiler_iterator(plat, compiler_replace_maps):

                    with open('%s.cmake' % (plat), 'wt') as f:

                        install_3rdparty_dependencies = True

                        includes_set = []
                        definitions_set = []
                        system_depends_set = []
                        depends_set = Set()

                        for package, platform_info in self.get_generator_targets(plat, compiler_c, compiler_cpp, ext_sta, ext_dyn):

                            package_lower = package.lower()
                            package_upper = package.upper()

                            if self.has_library(platform_info) and (package != 'dummy'):
                                f.write('if(NOT TARGET %s)\n\n' % package_lower)

                            try:
                                add_3rdparty_dependencies = platform_info['add_3rdparty_dependencies']
                            except KeyError:
                                add_3rdparty_dependencies = True

                            try:
                                lib_provided = platform_info['lib_provided']
                            except KeyError:
                                lib_provided = True

                            if 'include' in platform_info:
                                include = platform_info['include']
                                for d in include:
                                    includes_set.append(d)

                            # rename to definitions
                            if 'definitions' in platform_info:
                                definitions = platform_info['definitions']
                                for d in definitions:
                                    definitions_set.append(d)

                            if 'system_depends' in platform_info:
                                system_depends = platform_info['system_depends']
                                for sd in system_depends:
                                    system_depends_set.append(sd)

                            basename_compiler_cpp = os.path.basename(compiler_cpp)

                            if ('targets_paths' in self.parameters):
                                targets_paths = self.parameters['targets_paths']
                                for key, value in targets_paths.iteritems():
                                    f.write('file(TO_NATIVE_PATH "%s" %s)\n' % (value, key))

                            if ('executable' in platform_info) and (package != 'dummy'):
                                # a target in mode executable, dont need install
                                install_3rdparty_dependencies = False

                                if 'use_run_with_libs' in platform_info:
                                    if plat.startswith('win'):
                                        f.write('file(TO_NATIVE_PATH "${_MY_DIR}/../../run_with_libs.cmd" %s_LAUNCHER)\n' % package_upper)
                                    else:
                                        f.write('file(TO_NATIVE_PATH "${_MY_DIR}/../../run_with_libs.sh" %s_LAUNCHER)\n' % package_upper)

                                executable = platform_info['executable']
                                workbase = os.path.join(oldcwd, workspace, base_folder, plat, basename_compiler_cpp)
                                if not self.check_libs_exists(workbase, superpackage, package, executable, [('bin', True)], build_modes=['Release']):
                                    errors += 1
                                release_bin = self.get_lib_basename(workbase, executable, 'Release', 'bin')

                                for suffix in ['', '_EXECUTABLE']:
                                    if 'use_run_with_libs' in platform_info:
                                        f.write('set(%s%s "${%s_LAUNCHER}" "${_DIR}/%s/%s/%s" PARENT_SCOPE)\n' % (package_upper, suffix, package_upper, plat, basename_compiler_cpp, utils.get_norm_path(release_bin, native=False)))
                                    else:
                                        f.write('set(%s%s "${_DIR}/%s/%s/%s" PARENT_SCOPE)\n' % (package_upper, suffix, plat, basename_compiler_cpp, utils.get_norm_path(release_bin, native=False)))
                                    f.write('file(TO_NATIVE_PATH "${%s%s}" %s%s)\n' % (package_upper, suffix, package_upper, suffix))
                                f.write('\n')

                            if ('dynamic' in platform_info) and (package != 'dummy'):

                                dynamic = platform_info['dynamic']

                                # add depend
                                if add_3rdparty_dependencies:
                                    f.write('list(APPEND %s_LIBRARIES %s)\n' % (superpackage_upper, package_lower))

                                if plat.startswith('win'):
                                    workbase = os.path.join(oldcwd, workspace, base_folder, plat, basename_compiler_cpp)
                                    if not self.check_libs_exists(workbase, superpackage, package, dynamic, [('dll', True), ('lib', lib_provided), ('pdb', False)]):
                                        errors += 1

                                    debug_dll = self.get_lib_basename(workbase, dynamic, 'Debug', 'dll')
                                    release_dll = self.get_lib_basename(workbase, dynamic, 'Release', 'dll')
                                    relwithdebinfo_dll = self.get_lib_basename(workbase, dynamic, 'RelWithDebInfo', 'dll')
                                    minsizerel_dll = self.get_lib_basename(workbase, dynamic, 'Release', 'dll')

                                    debug_lib = self.get_lib_basename(workbase, dynamic, 'Debug', 'lib')
                                    release_lib = self.get_lib_basename(workbase, dynamic, 'Release', 'lib')
                                    relwithdebinfo_lib = self.get_lib_basename(workbase, dynamic, 'RelWithDebInfo', 'lib')
                                    minsizerel_lib = self.get_lib_basename(workbase, dynamic, 'Release', 'lib')

                                    try:
                                        # pdb is optional
                                        relwithdebinfo_pdb = 'RelWithDebInfo/%s' % self.get_lib(workbase, dynamic, 'RelWithDebInfo', 'pdb')
                                    except KeyError:
                                        relwithdebinfo_pdb = None
                                    except Exception as e:
                                        logging.debug('exception searching lib: %s' % e)
                                        relwithdebinfo_pdb = None

                                    try:
                                        debug_pdb = 'Debug/%s' % self.get_lib(workbase, dynamic, 'Debug', 'pdb')
                                        if self.is_invalid_lib(relwithdebinfo_pdb) and (not self.is_invalid_lib(debug_pdb)):
                                            relwithdebinfo_pdb = debug_pdb
                                    except KeyError:
                                        debug_pdb = None
                                    except Exception as e:
                                        logging.debug('exception searching lib: %s' % e)
                                        debug_pdb = None

                                    f.write('ADD_LIBRARY(%s SHARED IMPORTED)\n' % package_lower)
                                    f.write('SET_PROPERTY(TARGET %s APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)\n' % package_lower)
                                    f.write('SET_TARGET_PROPERTIES(%s PROPERTIES\n' % package_lower)

                                    # dll
                                    f.write('\tIMPORTED_LOCATION_DEBUG "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(debug_dll, native=False)))
                                    f.write('\tIMPORTED_LOCATION_RELEASE "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(release_dll, native=False)))
                                    f.write('\tIMPORTED_LOCATION_RELWITHDEBINFO "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(relwithdebinfo_dll, native=False)))
                                    f.write('\tIMPORTED_LOCATION_MINSIZEREL "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(minsizerel_dll, native=False)))
                                    f.write('\n')

                                    # lib
                                    if not self.is_invalid_lib(debug_lib):
                                        f.write('\tIMPORTED_IMPLIB_DEBUG "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(debug_lib, native=False)))
                                    if not self.is_invalid_lib(release_lib):
                                        f.write('\tIMPORTED_IMPLIB_RELEASE "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(release_lib, native=False)))
                                    if not self.is_invalid_lib(relwithdebinfo_lib):
                                        f.write('\tIMPORTED_IMPLIB_RELWITHDEBINFO "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(relwithdebinfo_lib, native=False)))
                                    if not self.is_invalid_lib(minsizerel_lib):
                                        f.write('\tIMPORTED_IMPLIB_MINSIZEREL "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(minsizerel_lib, native=False)))
                                    f.write('\n')

                                    # pdb
                                    if not self.is_invalid_lib(debug_pdb):
                                        f.write('\tIMPORTED_PDB_DEBUG "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(debug_pdb, native=False)))

                                    if not self.is_invalid_lib(relwithdebinfo_pdb):
                                        f.write('\tIMPORTED_PDB_RELWITHDEBINFO "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(relwithdebinfo_pdb, native=False)))

                                    f.write(')\n')
                                else:

                                    workbase = os.path.join(oldcwd, workspace, base_folder, plat, basename_compiler_cpp)
                                    if not self.check_libs_exists(workbase, superpackage, package, dynamic, [('so', True)]):
                                        errors += 1

                                    debug_so = self.get_lib_basename(workbase, dynamic, 'Debug', 'so')
                                    release_so = self.get_lib_basename(workbase, dynamic, 'Release', 'so')
                                    relwithdebinfo_so = self.get_lib_basename(workbase, dynamic, 'RelWithDebInfo', 'so')
                                    minsizerel_so = self.get_lib_basename(workbase, dynamic, 'Release', 'so')

                                    try:
                                        debug_so_full = os.path.join(oldcwd, workbase, debug_so)
                                        debug_soname = utils.get_soname(debug_so_full, env=env_modified)
                                    except Exception as e:
                                        logging.debug('exception searching lib: %s' % e)
                                        debug_soname = None

                                    try:
                                        release_so_full = os.path.join(oldcwd, workbase, release_so)
                                        release_soname = utils.get_soname(release_so_full, env=env_modified)
                                    except Exception as e:
                                        logging.debug('exception searching lib: %s' % e)
                                        release_soname = None

                                    try:
                                        relwithdebinfo_so_full = os.path.join(oldcwd, workbase, relwithdebinfo_so)
                                        relwithdebinfo_soname = utils.get_soname(relwithdebinfo_so_full, env=env_modified)
                                    except Exception as e:
                                        logging.debug('exception searching lib: %s' % e)
                                        relwithdebinfo_soname = None

                                    try:
                                        minsizerel_so_full = os.path.join(oldcwd, workbase, minsizerel_so)
                                        minsizerel_soname = utils.get_soname(minsizerel_so_full, env=env_modified)
                                    except Exception as e:
                                        logging.debug('exception searching lib: %s' % e)
                                        minsizerel_soname = None

                                    f.write('ADD_LIBRARY(%s SHARED IMPORTED)\n' % package_lower)
                                    f.write('SET_PROPERTY(TARGET %s APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)\n' % package_lower)
                                    f.write('SET_TARGET_PROPERTIES(%s PROPERTIES\n' % package_lower)

                                    # so
                                    f.write('\tIMPORTED_LOCATION_DEBUG "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(debug_so, native=False)))
                                    f.write('\tIMPORTED_LOCATION_RELEASE "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(release_so, native=False)))
                                    f.write('\tIMPORTED_LOCATION_RELWITHDEBINFO "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(relwithdebinfo_so, native=False)))
                                    f.write('\tIMPORTED_LOCATION_MINSIZEREL "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(minsizerel_so, native=False)))
                                    f.write('\n')

                                    # soname
                                    if (debug_soname is not None) and os.path.exists( os.path.join(os.path.dirname(debug_so_full), debug_soname) ):
                                        f.write('\tIMPORTED_SONAME_DEBUG "%s"\n' % utils.get_norm_path(debug_soname, native=False))

                                    if (release_soname is not None) and os.path.exists( os.path.join(os.path.dirname(release_so_full), release_soname) ):
                                        f.write('\tIMPORTED_SONAME_RELEASE "%s"\n' % utils.get_norm_path(release_soname, native=False))

                                    if (relwithdebinfo_soname is not None) and os.path.exists( os.path.join(os.path.dirname(relwithdebinfo_so_full), relwithdebinfo_soname) ):
                                        f.write('\tIMPORTED_SONAME_RELWITHDEBINFO "%s"\n' % utils.get_norm_path(relwithdebinfo_soname, native=False))

                                    if (minsizerel_soname is not None) and os.path.exists( os.path.join(os.path.dirname(minsizerel_so_full), minsizerel_soname) ):
                                        f.write('\tIMPORTED_SONAME_MINSIZEREL "%s"\n' % utils.get_norm_path(minsizerel_soname, native=False))

                                    f.write(')\n')

                            if ('static' in platform_info) and (package != 'dummy'):

                                static = platform_info['static']

                                workbase = os.path.join(oldcwd, workspace, base_folder, plat, basename_compiler_cpp)
                                if not self.check_libs_exists(workbase, superpackage, package, static, [('lib', True)]):
                                    errors += 1

                                debug_lib = self.get_lib_basename(workbase, static, 'Debug', 'lib')
                                release_lib = self.get_lib_basename(workbase, static, 'Release', 'lib')
                                relwithdebinfo_lib = self.get_lib_basename(workbase, static, 'RelWithDebInfo', 'lib')
                                minsizerel_lib = self.get_lib_basename(workbase, static, 'Release', 'lib')

                                if add_3rdparty_dependencies:
                                    # register target
                                    f.write('list(APPEND %s_LIBRARIES %s)\n' % (superpackage_upper, package_lower))

                                f.write('ADD_LIBRARY(%s STATIC IMPORTED)\n' % package_lower)
                                f.write('SET_PROPERTY(TARGET %s APPEND PROPERTY IMPORTED_CONFIGURATIONS DEBUG RELEASE RELWITHDEBINFO MINSIZEREL)\n' % package_lower)
                                f.write('SET_TARGET_PROPERTIES(%s PROPERTIES\n' % package_lower)

                                # lib
                                f.write('\tIMPORTED_LOCATION_DEBUG "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(debug_lib, native=False)))
                                f.write('\tIMPORTED_LOCATION_RELEASE "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(release_lib, native=False)))
                                f.write('\tIMPORTED_LOCATION_RELWITHDEBINFO "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(relwithdebinfo_lib, native=False)))
                                f.write('\tIMPORTED_LOCATION_MINSIZEREL "${_DIR}/%s/%s/%s"\n' % (plat, basename_compiler_cpp, utils.get_norm_path(minsizerel_lib, native=False)))

                                f.write(')\n')

                            if install_3rdparty_dependencies and (package != 'dummy'):
                                # install 3rd party
                                f.write('cmaki_install_3rdparty(%s)\n' % package_lower)
                            f.write('\n')

                            if self.has_library(platform_info) and (package != 'dummy'):
                                f.write('endif()\n\n')

                        # print includes
                        if len(includes_set) > 0:
                            # TODO: remove repeats
                            for d in list(set(includes_set)):
                                f.write('list(APPEND %s_INCLUDE_DIRS ${_DIR}/%s)\n' % (superpackage_upper, d))

                            f.write('\n')

                        if len(definitions_set) > 0:
                            # TODO: remove repeats
                            for d in list(set(definitions_set)):
                                f.write('add_definitions(%s)\n' % d)
                            f.write('\n')

                        if len(system_depends_set) > 0:
                            # TODO: remove repeats
                            f.write('# begin system depends\n')
                            for sd in list(set(system_depends_set)):
                                f.write('list(APPEND %s_LIBRARIES %s)\n' % (superpackage_upper, sd))
                            f.write('# end system depends\n')

                        if self.get_generate_find_package():
                            f.write('# Depends of %s (%s)\n' % (self.get_package_name(), self.get_version()))
                            for dep in self.get_depends_raw():
                                package_name = dep.get_package_name()
                                if package_name not in depends_set:
                                    if dep.have_any_in_target(plat, 'dynamic', compiler_replace_maps):
                                        f.write('cmaki_find_package(%s)\n' % (package_name))
                                    else:
                                        f.write('# cmaki_find_package(%s) # static package\n' % (package_name))
                                    depends_set.add(package_name)
                            f.write('\n')

                logging.info('----------------------------------------------------')
                if self.user_parameters.fast:
                    logging.debug('skipping for because is in fast mode: "generate_cmakefiles"')
                    break

        return errors

    def show_environment_vars(self, env_modified):
        package = self.get_package_name()
        logging.debug('------- begin print environment variables for compile %s ---------' % package)
        for key, value in sorted(env_modified.iteritems()):
            logging.debug("%s=%s" % (key, value))
        logging.debug('------- end print environment variables for compile %s -----------' % package)

    def create_toolchain_autogenerated(self, compiler_replace_maps):
        # windows dont need install toolchain in environment
        if utils.is_windows():
            return
        # for each platform and each compiler
        for plat in platforms:
            for compiler_c, compiler_cpp, _, ext_sta, ext_dyn, env_modified, env_new in self.compiler_iterator(plat, compiler_replace_maps):
                logging.info("generate _toolchain_autogenerated_%s" % os.path.basename(compiler_c))
                with open('_toolchain_autogenerated_%s' % os.path.basename(compiler_c), 'wt') as f:
                    f.write("""\
#!/bin/bash
SCRIPT_PATH=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PLATFORM=%s
""" % (plat))

                    for key, value in env_new.iteritems():
                        value = value.replace(self.user_parameters.toolchain, '${SCRIPT_PATH}')

                        if key in ['PATH']:
                            f.write("export %s=%s:$%s\n" % (key, value, key))
                        elif key in ['LD_LIBRARY_PATH']:
                            f.write("export %s=%s:$%s\n" % (key, value, key))
                        elif key in ['PYTHONPATH']:
                            f.write("export %s=%s:$%s\n" % (key, value, key))
                        else:
                            f.write("# %s=%s\n" % (key, value))

    def get_first_environment(self, compiler_replace_maps):
        for plat in platforms:
            for _, _, _, _, _, env_modified, _ in self.compiler_iterator(plat, compiler_replace_maps):
                return env_modified
        return os.environ.copy()

    def safe_system(self, cmd, compiler_replace_maps, log=False):
        return utils.safe_system(cmd, env=self.get_first_environment(compiler_replace_maps), log=log)

    def __repr__(self):
        return "%s - %s" % (self.name, self.parameters)

