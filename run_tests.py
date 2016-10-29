import os
import utils
import logging
from third_party import platforms
from third_party import build_unittests_foldername
from itertools import product

def run_tests(node, parameters, compiler_replace_maps, unittests):

    oldcwd = os.getcwd()

    cmakelib_dir = parameters.cmakefiles
    cmakelib_dir = utils.get_norm_path(cmakelib_dir)
    cmakelib_dir = cmakelib_dir.replace('\\', '/')

    cmake3p_dir = os.path.join(parameters.cmakefiles, '..', 'cmake3p')
    cmake3p_dir = utils.get_norm_path(cmake3p_dir)

    cmake_prefix = parameters.prefix
    cmake_prefix = cmake_prefix.replace('\\', '/')

    cmake_third_party_dir = parameters.third_party_dir
    cmake_third_party_dir = cmake_third_party_dir.replace('\\', '/')

    package = node.get_package_name()
    package_upper = node.get_package_name_norm_upper()
    version = node.get_version()
    packing = node.is_packing()
    if not packing:
        logging.warning("No need run_tests, because wasn't generated a package")
        return 0

    # prepare unittests
    # can be a file or content
    unittest_value = node.get_unittest()
    if unittest_value is not None:
        build_modes = node.get_build_modes()
        for plat, build_mode in product(platforms, build_modes):
            builddir = node.get_build_directory(plat, build_mode)
            path_test = os.path.join(builddir, build_unittests_foldername)
            utils.trymkdir(path_test)

            # is is a file
            unittest_path = os.path.join(builddir, unittest_value)
            if os.path.isfile(unittest_path):
                with open(unittest_path, 'rt') as f:
                    unittest_value = f.read()

            with open(os.path.join(path_test, 'main.cpp'), 'wt') as f:
                f.write(unittest_value)

            if parameters.fast:
                logging.debug('skipping for because is in fast mode: "prepare"')
                break
    else:
        logging.warning('[%s] No test present.' % package)

    folder_3rdparty = parameters.third_party_dir
    output_3rdparty = os.path.join(folder_3rdparty, node.get_base_folder())

    build_modes = node.get_build_modes()
    for plat, build_mode in product(platforms, reversed(build_modes)):
        for compiler_c, compiler_cpp, generator, _, _, env_modified, _ in node.compiler_iterator(plat, compiler_replace_maps):
            # verify md5sum
            workspace = node.get_workspace(plat)
            utils.trymkdir(workspace)
            with utils.working_directory(workspace):
                prefix_package = os.path.join(parameters.prefix, '%s.tar.gz' % workspace)
                prefix_package_md5 = os.path.join(output_3rdparty, '%s.md5' % workspace)
                if os.path.exists(prefix_package) and os.path.exists(prefix_package_md5):
                    with open(prefix_package_md5, 'rt') as f:
                        md5sum = f.read().strip()

                    try:
                        logging.debug("expected md5: %s" % md5sum)
                        for line in utils.get_stdout('cmake -E md5sum %s' % prefix_package, env_modified, 'cmake'):
                            if len(line) > 0:
                                # md5sum filename
                                chunks = line.split(' ')
                                chunks = filter(None, chunks)
                                assert(len(chunks) > 0)
                                md5sum_real = chunks[0]
                                logging.debug("real md5: %s" % md5sum_real)

                        if (md5sum != md5sum_real):
                            logging.error('Error en generated md5sum file!!!')
                            logging.error('Expected: %s' % md5sum)
                            logging.error('Found: %s' % md5sum_real)
                            # add error to node
                            node.ret += 1
                    except utils.NotFoundProgram:
                        logging.info('can\'t verify md5 because not found cmake')
                else:
                    logging.warning('Skipping verification md5 because don\'t exists package or md5')

            logging.info('running unittests. Build mode: %s Platform: %s' % (build_mode, plat))

            # remove cmake3p (and cmake3p of depends)
            node.remove_cmake3p( cmake3p_dir )
            builddir = os.path.join(oldcwd, node.get_build_directory(plat, build_mode))
            logging.info('Using builddir %s' % builddir)
            unittest_folder = os.path.join(builddir, build_unittests_foldername)
            unittest_found = os.path.join(unittest_folder, 'main.cpp')
            unittest_found = unittest_found.replace('\\', '/')
            unittest_root = os.path.join(oldcwd, build_unittests_foldername)

            if os.path.exists(unittest_found):

                logging.info('Search cmakelib in %s' % cmakelib_dir)
                if os.path.exists(os.path.join(cmakelib_dir, 'setup_projects.cmake')):

                    with utils.working_directory(unittest_folder):

                        generator_extra = ''
                        if generator is not None:
                            generator_extra = '-G"%s"' % generator

                        # remove CMakeCache.txt for avoid problems when
                        # change of generator
                        utils.tryremove('CMakeCache.txt')
                        utils.tryremove('cmake_install.cmake')
                        utils.tryremove('install_manifest.txt')
                        utils.tryremove_dir('CMakeFiles')

                        cmd = 'cmake %s %s -DCMAKE_MODULE_PATH=%s -DPACKAGE=%s -DPACKAGE_UPPER=%s -DCMAKE_BUILD_TYPE=%s -DAVOID_USE_HTTP=1 -DINSTALL_SIMPLE=1 -DCMAKE_PREFIX_PATH=%s -DUNITTEST_PATH=%s -DGTC_PREFIX=%s && cmake --build . --config %s --target install && ctest . -C %s --output-on-failure -VV' % (unittest_root, generator_extra, cmakelib_dir, package, package_upper, build_mode, cmake_third_party_dir, unittest_found, cmake_prefix, build_mode, build_mode)
                        ret = utils.safe_system(cmd, env=env_modified)
                        node.ret += abs(ret)
                        if ret != 0:
                            unittests[ '%s - %s' % (package, version) ] = 'ERROR: Fail test'
                        else:
                            unittests[ '%s - %s' % (package, version) ] = 'OK: Pass test'
                else:
                    unittests[ '%s - %s' % (package, version) ] = 'WARN: No cmakelib available'
            else:
                unittests[ '%s - %s' % (package, version) ] = 'WARN: No unittest found'

        if parameters.fast:
            logging.debug('skipping for because is in fast mode: "run_tests"')
            break

    # finish well
    return True

