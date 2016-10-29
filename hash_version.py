import os
import re
import subprocess
import colorama
import contextlib
import utils
from termcolor import colored
from utils import get_stdout

def get_revision_svn(repo):
    '''
    This command need svn in PATH
    '''
    cmd = "svn info %s" % repo
    for line in get_stdout(cmd):
        if line.startswith('Last') or (line.startswith('Revisi') and (line.find('cambio') != -1)):
            pos = line.rindex(':')
            return int(line[pos+2:])
    return -1

def get_revision_git(repo, number = 1):

    with utils.working_directory(repo):
        for line in get_stdout('git log -%d %s | grep ^commit' % (number, repo)):
            parts = line.split(' ')
            assert(len(parts) == 2)
            commit_name = parts[1]
            yield commit_name

def get_one_revision_git(repo, short=True):
    for changeset in get_revision_git(repo):
        if short:
            return changeset[:7]
        else:
            return changeset
    return ""

def get_position_changeset(repo, changeset):
    with working_directory(repo):
        for c in get_stdout('git rev-list %s --count --first-parent' % changeset):
            try:
                return int(c)
            except ValueError:
                return 0
    return -1

def rehash_simple(commit_name):
    add = 0
    for c in commit_name:
        add += ord(c)
    return add

@contextlib.contextmanager
def working_directory(path):
    prev_cwd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev_cwd)

def to_cmaki_version(repo, changeset):
    position = get_position_changeset(repo, changeset)
    hash_simple = rehash_simple(changeset)
    versions = []
    versions.append('0')
    versions.append('0')
    versions.append(str(position))
    versions.append(str(hash_simple))
    return '.'.join(versions)

if __name__ == '__main__':

    # print(Fore.RED + 'some red text')
    # print(Back.GREEN + 'and with a green background')
    # print(Style.DIM + 'and in dim text')
    # print(Style.RESET_ALL)
    # print('back to normal now')

    remote_revision = get_revision_svn('https://github.com/makiolo/cmaki')
    #print "https://github.com/makiolo/cmaki -> %s" % remote_revision

    print get_one_revision_git('/home/makiolo/dev/fann_test/cmaki')

    for commit_name in get_revision_git('/home/makiolo/dev/fann_test/cmaki', 10):

        cmaki_version = to_cmaki_version('/home/makiolo/dev/fann_test/cmaki', commit_name)
        print "%s -> %s" % (commit_name, cmaki_version)

