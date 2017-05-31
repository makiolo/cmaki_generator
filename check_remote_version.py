import os
import sys
import logging
import argparse
import urllib
import cStringIO
import csv
import utils

def read_remote_csv(url):
    f = urllib.urlopen(url)
    try:
        csv = f.read()
    finally:
        f.close()
    return csv

version_separator = '.'
version_count_max = 4

def version_to_tuple(version_str):
    try:
        if (version_str is not None) and (len(version_str) > 0):
            count = len(version_str.split(version_separator))
            list_data = [int(x) for x in version_str.split(version_separator)]
            zeros = [0 for x in range(version_count_max - count)]
            list_data.extend(zeros)
            return tuple(list_data)
        else:
            return None
    except ValueError:
        return None

class package(object):
    def __init__(self, name,  version, local):
        self._name = name
        self._version = version_to_tuple(version)
        self._local = local
    def __repr__(self):
        if self._version is not None:
            list_version = list(self._version)
            list_version = [str(x) for x in list_version]
            join_version = version_separator.join(list_version)
        else:
            join_version = "last"
        return "%s;%s" % (self._name, join_version)

    def __eq__(self, other):
        return (self._name == other._name) or (self._name == '.') or (other._name == '.')

    def __ne__(self, other):
        return not self.__eq__(other)

    def is_same_version(self, other):
        return self._version == other._version

    def get_name(self):
        return self._name

    def get_version(self):
        return self._version

    def is_local(self):
        return self._local

def sort_versions(local_swap):
    if not local_swap:
        one = 1
    else:
        one = -1
    def cmp(a, b):
        if a.get_version() < b.get_version():
            return 1
        elif a.get_version() > b.get_version():
            return -1
        else:
            if a.is_local() and not b.is_local():
                return -one
            elif a.is_local() and b.is_local():
                return one
            elif not a.is_local() and b.is_local():
                return one
            else:
                return one
    return cmp

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', dest='artifacts', help='3rdparty path with cmakefiles', default=None)
    parser.add_argument('--server', dest='server', help='artifact server', default=None)
    """
    Existe un valor especial de name ".". Sirve para hacer un listado de todos los artefactos
    """
    parser.add_argument('--name', required=True, dest='name', help='name package', default=None)
    """
    La version fijada tiene la siguiente prioridad:
        - Version fijada mediante parametros
        - Version fijada mediante fichero de dependencias
        - Version ultima
    """
    parser.add_argument('--version', dest='version', help='version package fixed', default=None)
    parser.add_argument('--platform', dest='platform', help='platform specified', default=None)
    parameters = parser.parse_args()

    package_request = package(parameters.name, parameters.version, True)
    packages_found = []

    if parameters.artifacts is not None:
        # local
        utils.trymkdir(parameters.artifacts)
        for path in os.listdir(parameters.artifacts):
            fullpath = os.path.join(parameters.artifacts, path)
            # directorios que contengan "-"
            if os.path.isdir(fullpath) and (fullpath.find('-') != -1):
                basename = os.path.basename(fullpath)
                try:
                    separator = basename.rindex('-')
                    package_name = basename[:separator]
                    package_version =  basename[separator+1:]
                    new_package = package(package_name, package_version, True)
                    if new_package == package_request:
                        packages_found.append(new_package)
                except ValueError:
                    pass  # happen with 3rdpartyversions

    """
    Buscar paquetes recien generados
    """
    if parameters.artifacts is not None:
        # local
        for path in os.listdir(parameters.artifacts):
            fullpath = os.path.join(parameters.artifacts, path)
            terminator = '-cmake.tar.gz'
            if os.path.isfile(fullpath) and (fullpath.endswith(terminator)):
                if parameters.platform is None:
                    logging.error('Platform is needed!')
                    sys.exit(1)
                terminator = '-%s-cmake.tar.gz' % parameters.platform
                basename = os.path.basename(fullpath)
		try:
		        separator = basename.rindex(terminator)
		        basename = basename[:separator]
		        separator = basename.rindex('-')
		        package_name = basename[:separator]
		        package_version =  basename[separator+1:]
		        new_package = package(package_name, package_version, True)
		        if new_package == package_request:
		            packages_found.append(new_package)
		except ValueError:
			# not found platform in file
			pass

    if parameters.server is not None:
        try:
            if not parameters.server.endswith('?quiet'):
                parameters.server = parameters.server + '/' + '?quiet'
            csv_content = read_remote_csv(parameters.server)
            reader = csv.reader(cStringIO.StringIO(csv_content), delimiter=';')
            i = 0
            for row in reader:
                if len(row) >= 2:
                    if i > 0:
                        package_name = row[0]
                        package_version = row[1]
                        package_platform = row[2]
                        new_package = package(package_name, package_version, False)
                        if (parameters.platform is None) or (parameters.platform == package_platform):
                            if new_package == package_request:
                                packages_found.append(new_package)
                    i += 1
        except IOError:
            logging.debug('error in cache artifacts: %s' % parameters.server)

    if len(packages_found) > 0:

        if (parameters.version is None):
            """
            Cuando no hay version, ordeno de mayor a menor.
            Al pasar False al comparador aparece primero local y luego remote en caso de ser la misma version.
            Selecciona el primero y sale.
            """
            for package in sorted(packages_found, cmp=sort_versions(False)):
                if package_request.is_same_version(package):
                    print("EXACT;%s" % (package))
                else:
                    print("COMPATIBLE;%s" % (package))
                if parameters.name != '.':
                    sys.exit(0)
        else:
            """
            Cuando se especifica una version minima
            Se ordena a la inversa, es decir de menor a mayor.
            Se coge el primer paquete que cumple la restriccion de version.
            Al pasar True al comparador hace que en caso de empate se mantenga a pesar del reverse que
            aparece primero versiones locales y luego las remotas.
            """
            for package in sorted(packages_found, cmp=sort_versions(True), reverse=True):
                if(package.get_version() >= package_request.get_version()):
                    if package_request.is_same_version(package):
                        print("EXACT;%s" % (package))
                    else:
                        print("COMPATIBLE;%s" % (package))
                    if parameters.name != '.':
                        sys.exit(0)
    else:
        print("UNSUITABLE;")
        sys.exit(1)

