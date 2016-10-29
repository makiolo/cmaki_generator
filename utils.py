import os
import re
import sys
import shutil
import logging
import glob
import subprocess
import urllib2
import tarfile
import zipfile
import time
import contextlib
import hashlib
import yaml
import json
import errno
from distutils.spawn import find_executable
try:
    import bz2
    python_has_bz2 = True
except ImportError:
    logging.debug('python module bz2 built-in is not available')
    python_has_bz2 = False

class NotFoundProgram(Exception):
    def __init__(self, msg):
        self._msg = msg
    def __repr__(self):
        return "%s" % self._msg

def is_windows():
    return sys.platform.startswith("win")

def smart_merge(dict1, dict2):
    assert(dict1 is not None)
    assert(dict2 is not None)
    for key, value in dict2.items():
        if isinstance(value, dict):
            try:
                dict1[key].update(value)
            except KeyError:
                dict1[key] = value
        else:
            try:
                dict1[key] += value
            except TypeError:
                dict1[key] = value
            except KeyError:
                dict1[key] = value
    return dict1

def apply_replaces(element, dictionary):
    if isinstance(element, dict):
        new = {}
        for k,v in element.iteritems():
            new[k] = apply_replaces(v, dictionary)
        return new
    elif isinstance(element, list):
        new = []
        for e in element:
            new.append( apply_replaces(e, dictionary) )
        return new
    elif isinstance(element, bool):
        return element
    elif element is not None:
        new_element = str(element)
        for k,v in dictionary.iteritems():
            # find in original, not in replaced
            if str(element).find(k) != -1:
                new_element = new_element.replace(k, v)
        return new_element
    else:
        return None

def apply_replaces_vars(element, dictionary):
    newdict = {}
    for k,v in dictionary.iteritems():
        newdict['$%s' % k] = v
        newdict['${%s}' % k] = v
    return apply_replaces(element, newdict)

def tryremove(filename):
    try:
        logging.debug('Removing file %s' % (filename))
        os.remove(filename)
    except OSError:
        pass

def _tryremove_dir(directory):
    if os.path.isdir(directory):
        i = 0
        tries = 3
        while i < tries:
            try:
                shutil.rmtree(directory)
                if not os.path.exists(directory):
                    i = tries + 1
            except OSError:
                logging.debug('Fail removing %s. Retry %d/%d' % (directory, i, tries))
                time.sleep(1)
            finally:
                i += 1

def tryremove_dir(source):
    logging.debug('Removing directory %s' % (source))
    _tryremove_dir(source)

def tryremove_dir_empty(source):
    try:
        os.rmdir(source)
    except OSError as ex:
        if ex.errno != errno.ENOTEMPTY:
            logging.debug('Removing empty directory %s' % (source))

def download_from_url(url, filename):
    logging.debug('Download from url %s' % url)
    logging.debug("Download to file %s" % (filename))
    if not os.path.exists(filename):
        download_dirname = os.path.dirname(filename)
        download_basename = os.path.basename(filename)
        with working_directory(download_dirname):
            u = urllib2.urlopen(url)
            with open(download_basename, 'wb') as f:
                file_size_dl = 0
                block_sz = 8192
                while True:
                    buffer = u.read(block_sz)
                    if not buffer:
                        break
                    file_size_dl += len(buffer)
                    f.write(buffer)
    else:
        logging.warning('skipping download, already exists %s' % filename)

def setup_logging(level, logname):
    dirlog = os.path.dirname(logname)
    if dirlog != '':
        trymkdir(dirlog)
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    if(len(logging.root.handlers) == 1):
        logging.root.removeHandler( logging.root.handlers[0] )
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter('%(asctime)s %(name)-12s: %(levelname)-8s %(message)s'))
    logger.addHandler(handler)
    handler2 = logging.FileHandler(logname)
    handler2.setLevel(logging.DEBUG)
    handler2.setFormatter(logging.Formatter('%(asctime)s %(name)-12s: %(levelname)-8s %(message)s'))
    logger.addHandler(handler2)

def prompt_yes_no(default = False):
    # raw_input returns the empty string for "enter"
    yes = set(['yes','y', 'ye', ''])
    no = set(['no','n'])

    choice = raw_input().lower()
    if choice in yes:
        return True
    elif choice in no:
        return False
    else:
        sys.stdout.write("Please respond with 'yes' or 'no'")
    return default

def show_element(element, deep = 0):
    if isinstance(element, dict):
        for k,v in element.iteritems():
            logging.info("%s<%s>" % ('\t'*deep, k))
            show_element(v, deep + 1)
    elif isinstance(element, list):
        for e in element:
            show_element(e, deep + 1)
    else:
        logging.info('%s%s' % ('\t'*deep, element))

def _rec_glob(result, rootdir, pattern, deep_max, exclusions, deep):
    if(os.path.isdir(rootdir)):
        if deep < deep_max:
            for folder in os.listdir(rootdir):
                fullpath = os.path.join(rootdir, folder)
                if os.path.isdir(fullpath):
                    _rec_glob(result, fullpath, pattern, deep_max, exclusions, deep + 1)
        for fullpath in glob.glob(os.path.join(rootdir, pattern)):
            # ignore some stuff
            for exc in exclusions:
                if fullpath.endswith(exc):
                    break
            else:
                # process file
                result.append( os.path.abspath(fullpath) )

def rec_glob(rootdir, pattern, deep_max=99, exclusions=[]):
    result = []
    _rec_glob(result, rootdir, pattern, deep_max, exclusions, 0)
    return result

def trymkdir(directory):
    if not os.path.exists( directory ):
        os.makedirs( directory )

def move_folder_recursive(source, destiny):
    if not os.path.exists(source):
        raise Exception('Error in move_folder_recursive: source not exists: %s' % source)
    for archive in os.listdir(source):
        # ignore some stuff
        if archive.startswith('.git') or archive.startswith('.svn'):
            continue
        archive2 = os.path.join(source, archive)
        destiny2 = os.path.join(destiny, archive)
        if(os.path.isdir(archive2)):
            move_folder_recursive(archive2, destiny2)
        else:
            if os.path.isfile(destiny2):
                logging.debug('Replacing file %s' % destiny2)
                tryremove(destiny2)
            # try create destiny directory
            trymkdir( os.path.dirname(destiny2) )
            # move file
            shutil.move(archive2, destiny2)

def copy_folder_recursive(source, destiny):
    if not os.path.exists(source):
        raise Exception('Error in copy_folder_recursive: source not exists: %s' % source)
    for archive in os.listdir(source):
        # ignore some stuff
        if archive.startswith('.git') or archive.startswith('.svn'):
            continue
        archive2 = os.path.join(source, archive)
        destiny2 = os.path.join(destiny, archive)
        if(os.path.isdir(archive2)):
            copy_folder_recursive(archive2, destiny2)
        else:
            if os.path.isfile(destiny2):
                logging.debug('Replacing file %s' % destiny2)
                tryremove(destiny2)
            # try create destiny directory
            trymkdir( os.path.dirname(destiny2) )
            # copy file (and stat)
            shutil.copy2(archive2, destiny2)

def extract_file(path, to_directory, environment):

    # convert to absolute
    logging.debug('Extract file %s' % path)
    path = os.path.abspath(path)

    if path.endswith('.zip'):
        opener, mode = zipfile.ZipFile, 'r'
    elif path.endswith('.tar.gz') or path.endswith('.tgz'):
        opener, mode = tarfile.open, 'r:gz'
    elif path.endswith('.tar.bz2') or path.endswith('.tbz'):
        # python have problems with big .tar.bz2 in windows
        if is_windows():
            with working_directory(to_directory):
                logging.debug('Using cmake -E tar for package: %s' % path)
                ret = safe_system('cmake -E tar xvf %s' % path, env=environment)
                ok = (ret == 0)

            # be careful, early return
            return ok
        else:
            if python_has_bz2:
                opener, mode = tarfile.open, 'r:bz2'
            else:
                logging.warning('Not using python-bz2 module for uncompress: %s in %s' % (path, to_directory))
                with working_directory(to_directory):
                    logging.debug('Using bunzip2 and tar for package: %s' % path)
                    ret = safe_system('bunzip2 -c %s | tar xvf -' % path, env=environment)
                    ok = (ret == 0)

                # be careful, early return
                return ok
    elif path.endswith('.tar.xz'):
        # needd "xz"
        with working_directory(to_directory):
            ret = safe_system('tar xpvf %s' % path, env=environment)
            ok = (ret == 0)
            return ok
    else:
        raise ValueError, "Could not extract `%s` as no appropriate extractor is found" % path

    # create directory if not exists
    trymkdir(to_directory)
    with working_directory(to_directory):
        file = opener(path, mode)
        try:
            file.extractall()
        finally:
            file.close()
    return True

# Copy Paste from run_tests (handler.py)
def detect_ncpus():
    """Detects the number of effective CPUs in the system.
    if the there is variable called FOL_NUMBER_OF_PROCESSORS_OVERRIDE detect_ncpus will return its value"""
    nprocessors_override = os.environ.get("FOL_NUMBER_OF_PROCESSORS_OVERRIDE", None)
    if (nprocessors_override != None):
        if isinstance(nprocessors_override, int) and nprocessors_override > 0:
            return nprocessors_override
        elif isinstance(nprocessors_override, str):
            return int(nprocessors_override)
    else:
        #for Linux, Unix and MacOS
        if hasattr(os, "sysconf"):
            if os.sysconf_names.has_key("SC_NPROCESSORS_ONLN"):
                #Linux and Unix
                ncpus = os.sysconf("SC_NPROCESSORS_ONLN")
                if isinstance(ncpus, int) and ncpus > 0:
                    return ncpus
            else:
                #MacOS X
                ncpus = int(os.popen2("sysctl -n hw.ncpu")[1].read())
                return ncpus
        #for Windows
        if os.environ.has_key("NUMBER_OF_PROCESSORS"):
            ncpus = int(os.environ["NUMBER_OF_PROCESSORS"]);
            if ncpus > 0:
                return ncpus
        #return the default value
        return 1

def get_norm_path(pathfile, native=True):
    if native and is_windows():
        return pathfile.replace('/', '\\')
    else:
        return pathfile.replace('\\', '/')

def get_filename_no_ext(filename):
    return os.path.splitext(filename)[0]

def get_soname(libfile, env=os.environ.copy()):

    if is_windows():
        logging.error('get_soname is not supported in windows')
        return

    cmd = ['objdump', "-p", libfile]
    for line in get_stdout(cmd, env, 'objdump'):
        if line.find('SONAME') != -1:
            return line.split()[1]
    raise Exception('No soname detected in %s' % libfile)

def get_needed(libfile, env=os.environ.copy()):

    if is_windows():
        logging.error('get_needed is not supported in windows')
        return

    cmd = ['objdump', "-p", libfile]
    for line in get_stdout(cmd, env, 'objdump'):
        if line.find('NEEDED') != -1:
            yield line.split()[1]

'''
Example use, in ldgrd105:
/us/xatemb1d is a symbolic link to /pr/us/xatemb1d
'''
def get_real_home():
    if sys.platform.startswith("sun"):
        # problems launching subshell in solaris
        return os.environ['HOME']
    else:
        cmd = "REAL_HOME=$(cd $HOME && pwd -P) && echo $REAL_HOME"
        for line in get_stdout(cmd):
            return line
        return os.environ['HOME']

@contextlib.contextmanager
def working_directory(path):
    prev_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)

def walklevel(some_dir, level=1):
    '''
    os.walk() with max level
    '''
    some_dir = some_dir.rstrip(os.path.sep)
    assert os.path.isdir(some_dir)
    num_sep = some_dir.count(os.path.sep)
    for root, dirs, files in os.walk(some_dir):
        yield root, dirs, files
        num_sep_this = root.count(os.path.sep)
        if num_sep + level <= num_sep_this:
            del dirs[:]

def get_revision_svn(repo, path_svn='svn', env=os.environ.copy()):
    '''
    This command need svn in PATH
    '''
    if os.path.exists(repo):
        with working_directory(repo):
            env_copy = env.copy()
            svn_bin = os.path.abspath(os.path.join(os.path.dirname(path_svn), '..', 'bin'))
            svn_lib = os.path.abspath(os.path.join(os.path.dirname(path_svn), '..', 'lib'))
            env_copy['PATH'] = "%s:%s" % (svn_bin, env_copy['PATH'])
            env_copy['LD_LIBRARY_PATH'] = "%s:%s" % (svn_lib, env_copy['LD_LIBRARY_PATH'])
            cmd = "%s info" % path_svn
            p = subprocess.Popen(cmd, shell=True, stdout = subprocess.PIPE, stderr = subprocess.PIPE, universal_newlines=True, env=env_copy)
            data, err = p.communicate()

            # clean stdout
            data = [line.strip() for line in data.split('\n') if line.strip()]

            for line in data:
                separator = 'Last Changed Rev: '
                if line.startswith(separator):
                    return int(line[len(separator):])
                else:
                    separator = 'Revisi.n del .ltimo cambio: '
                    if re.match(separator, line) is not None:
                        return int(line[len(separator):])
    return -1

def verbose(parameters, msg):
    if parameters.verbose > 0:
        logging.info(msg)

def superverbose(parameters, msg):
    if parameters.verbose > 1:
        logging.info(msg)

def hyperverbose(parameters, msg):
    if parameters.verbose > 2:
        logging.info(msg)

def md5sum(filename, blocksize=65536):
    hash = hashlib.md5()
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(blocksize), b""):
            hash.update(block)
    return hash.hexdigest()

def serialize(pythonDict, fileName):
    # serialiedData = json.dumps(pythonDict)
    serialiedData = yaml.dump(pythonDict, default_flow_style=True)
    with open(fileName, 'wt') as f:
        f.write(serialiedData)

def deserialize(fileName):
    with open(fileName, 'rt') as f:
        stringData = f.read()
    # return json.loads(stringData)
    return yaml.load(stringData)

def serialize_json(pythonDict, fileName):
    serialiedData = json.dumps(pythonDict)
    with open(fileName, 'wt') as f:
        f.write(serialiedData)

def deserialize_json(fileName):
    with open(fileName, 'rt') as f:
        stringData = f.read()
    return json.loads(stringData)

def get_stdout(cmd, env=os.environ.copy(), program_required=None):
    if isinstance(cmd, list):
        cmd = ' '.join(cmd)
    logging.debug('launch cmd: %s' % cmd)

    # search executable
    ok = True
    if program_required is not None:
        ok = find_executable(program_required, env['PATH'])
    if ok:
        p = subprocess.Popen(cmd, shell=True, stdout = subprocess.PIPE, stderr = subprocess.STDOUT, universal_newlines=True, env=env)
        data, err = p.communicate()
        data = [line.strip() for line in data.split('\n') if line.strip()]
        for line in data:
            logging.debug('[out cmd] %s' % line)
            yield line
    else:
        raise NotFoundProgram('Not found program %s, for execute: %s' % (program_required, cmd))

def safe_system(cmd, env=os.environ.copy()):
    logging.debug("exec command: %s" % cmd)
    p = subprocess.Popen(cmd, shell=True, stdout = subprocess.PIPE, stderr = subprocess.STDOUT, universal_newlines=True, env=env)
    data, err = p.communicate()
    data = [line for line in data.split('\n')]
    if p.returncode != 0:
        logging.error("begin@output: %s" % cmd)
    for line in data:
        if p.returncode != 0:
            if (line.lower().find('error') != -1) or (line.lower().find('fatal') != -1):
                logging.error(line)
            else:
                logging.warning(line)
        else:
            logging.debug(line)
    if p.returncode != 0:
        logging.error("end@output: %s" % cmd)
    return p.returncode

