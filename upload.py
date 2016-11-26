import os
import logging
import utils
from third_party import platforms


def upload(node, parameters, compiler_replace_maps):

    if parameters.server is None:
        logging.error('parameter --server is mandatory for upload')
        return False

    # pack tar.gz binaries
    for plat in platforms:
        workspace = node.get_workspace(plat)
        prefix_package = os.path.join(parameters.prefix, '%s.tar.gz' % workspace)
        command = "python upload_package.py --url=%s/upload.php --filename=%s" % (parameters.server, prefix_package)
        node.ret += abs(utils.safe_system(command))

    # pack cmakefiles
    if not parameters.no_packing_cmakefiles:
        for plat in platforms:
            base_folder = node.get_base_folder()
            prefix_package_cmake = os.path.join(parameters.prefix, '%s-%s-cmake.tar.gz' % (base_folder, plat))
            command = "python upload_package.py --url=%s/upload.php --filename=%s" % (parameters.server, prefix_package_cmake)
            node.ret += abs(utils.safe_system(command))

    return True

