import os
import os.path
import sys
import fnmatch
import logging
import utils
import argparse
import pipeline
import traceback
import copy
import datetime
# object package
from third_party import ThirdParty
from collections import OrderedDict
from third_party import exceptions_fail_group
from third_party import exceptions_fail_program
from third_party import alias_priority_name
from third_party import alias_priority_name_inverse
from third_party import CMAKELIB_URL
from third_party import is_valid
from third_party import is_blacklisted
# gtc stages
from purge import purge
from prepare import prepare
from compilation import compilation
from packing import packing
from run_tests import run_tests
from upload import upload
from get_return_code import get_return_code
from third_party import FailThirdParty
from utils import download_from_url

# GLOBAL NO MUTABLES
image_pattern = "image.%Y.%m.%d.%H%M"

try:
    import yaml
except ImportError:
    logging.error('[Warning] Not yaml library present')
    logging.error('[Warning] PyYAML (python extension) is mandatory')
    if utils.is_windows():
        logging.error('You can use pip for install:')
        logging.error('    pip intall pyyaml')
    sys.exit(1)

# Global mutable
compiler_replace_maps = {}

# Global const
yaml_common_references = 'common.yml'
yaml_collapsed_third_parties = '.3p.yml'
yaml_collapsed_final = '.data.yml'

class Loader(yaml.Loader):
    def __init__(self, stream):
        self._root = os.path.split(stream.name)[0]
        super(Loader, self).__init__(stream)

    def include(self, node):
        filename = os.path.join(self._root, self.construct_scalar(node))
        with open(filename, 'r') as f:
            return yaml.load(f, Loader)

def amalgamation_yaml(rootdir):
    Loader.add_constructor('!include', Loader.include)

    # autogeneration .data.yml
    with open(yaml_collapsed_final, 'wt') as f:
        f.write('# autogenerated file, dont edit it !!!---\n')
        f.write('---\n')
        # inject common.yml
        f.write('%sreferences:\n' % (' '*4))
        with open(yaml_common_references, 'r') as fr:
            for line in fr.readlines():
                f.write('%s%s' % (' '*8, line))
        collapse_third_parties(rootdir, yaml_collapsed_third_parties)
        # inject third_parties.yml
        f.write('%sthird_parties:\n' % (' '*4))
        with open(yaml_collapsed_third_parties) as ft:
            for line in ft.readlines():
                f.write('%s%s' % (' '*8, line))

def search_nodes_by_key(list_nodes, found_key):
    nodes = []
    for key, node in list_nodes:
        if key == found_key:
            nodes.append(node)
    return nodes

def collapse_third_parties(rootdir, filename):
    p = pipeline.make_pipe()
    # begin
    p = pipeline.find(rootdir, 3)(p)
    p = pipeline.endswith('.yml')(p)
    # exclusions
    p = pipeline.grep_v('.build_')(p)
    p = pipeline.grep_v('.bs_')(p)
    p = pipeline.grep_v('.travis.yml')(p)
    p = pipeline.grep_v('shippable.yml')(p)
    p = pipeline.grep_v('appveyor.yml')(p)
    p = pipeline.grep_v('depends.json')(p)
    p = pipeline.grep_v(yaml_collapsed_final)(p)
    p = pipeline.grep_v(yaml_common_references)(p)
    p = pipeline.grep_v(yaml_collapsed_third_parties)(p)
    p = pipeline.grep_v(' - Copy.yml')(p)
    # cat
    p = pipeline.cat()(p)
    # write
    p = pipeline.write_file(filename)(p)
    # end
    pipeline.end_pipe()(p)

def run_purge(solutions):

    # create pipeline
    with pipeline.create() as (p, finisher):

        # feed all packages
        p = pipeline.feed(packages)(p)

        # clean intermediate folders
        p = pipeline.do(purge, True, parameters)(p)

        # close pipe
        finisher.send(p)

def convert_priority_to_integer(priority):
    if priority is not None:
        error = False
        if priority in alias_priority_name_inverse:
            priority = alias_priority_name_inverse[priority]
        else:
            try:
                priority_integer = int(priority)
                if priority_integer in alias_priority_name:
                    priority = priority_integer
                else:
                    error = True
            except ValueError:
                error = True
        if error:
            logging.error('Invalid priority name: %s' % priority)
            sys.exit(1)
    return priority

def show_results(parameters, groups_ordered, rets, unittests):
    # show final report
    anyFail = 0
    if len(rets) > 0:
        logging.info('-' * 80)
        logging.info('')
        for name in rets:
            state = rets[name]
            if state != "OK":
                anyFail = 1

            # package with unittests?
            if name in unittests:
                try:
                    result_test = unittests[name]
                except KeyError:
                    result_test = 'No unittest found'

                if state != "OK":
                    logging.info("Compiled %30s - STATUS: %15s" % (name, state))
                else:
                    # only want know test result if is OK
                    logging.info("Compiled %30s - STATUS: %15s - TESTS: %s" % (name, state, result_test))
            else:
                logging.info("Compiled %30s - STATUS: %15s" % (name, state))

        logging.info('')
        logging.info( '-'* 80)
        if toolchain_povided:
            logging.info('Compiled with this toolchain: --toolchain=%s' % parameters.toolchain)
            logging.info( '-'* 80)
    else:
        anyFail = 1
        logging.error('No results generated.')

    # any have exceptions ?
    have_exceptions = False
    for _, packages in groups_ordered:
        for node in packages:
            if len(node.exceptions) > 0:
                have_exceptions = True

    if have_exceptions:
        logging.error("---------- begin summary of exceptions ------------------------")
        # show postponed exceptions
        for _, packages in groups_ordered:
            for node in packages:
                if len(node.exceptions) > 0:
                    # something was wrong
                    anyFail = 1
                    # show exceptions of this package
                    package = node.get_package_name()
                    version = node.get_version()
                    logging.error("package %s (%s) with exceptions" % (package, version))
                    i = 0
                    for exc_type, exc_value, exc_traceback in node.exceptions:
                        logging.error("---- Exception #%d / %d ----------" % (i+1, len(node.exceptions)))
                        traceback.print_exception(exc_type, exc_value, exc_traceback)
                        logging.error("----------------------------------")
                        i += 1
        logging.error("---------- end summary of exceptions ------------------------")
    return anyFail

def clean_subset(solutions):
    groups = copy.deepcopy(solutions)
    # 2/4: remove solutions are subset of other solution
    for solution1 in solutions:
        for solution2 in solutions:
            if solution1 != solution2:
                match = True
                for node in solution1:
                    if node not in solution2:
                        match = False
                        break
                if match and (solution1 in groups):
                    groups.remove(solution1)
    return groups

def prepare_cmakelib(parameters):
    # if os.path.isdir(os.path.join(parameters.cmakefiles)):
    #     utils.tryremove_dir(parameters.cmakefiles)
    utils.safe_system('git clone --recursive %s %s' % (CMAKELIB_URL, parameters.cmakefiles))

def init_parameter_path(value, default):
    if value is None:
        value = default
    else:
        # expand variables in no-windows
        if not utils.is_windows():
            value = value.replace('~', utils.get_real_home())
        value = os.path.abspath(value)
    return value

if __name__ == '__main__':

    parser = argparse.ArgumentParser(prog="""

cmaki_generator:

    Can build artifacts in a easy way. Each third-party need a block definition in yaml. This block contain all need information necessary for download, build, testing and packing.

usage:""")
    group_main = parser.add_argument_group('basic usage')
    group_main.add_argument('packages', metavar='packages', type=str, nargs='+', help='name (or list names) third party')
    group_main.add_argument('--plan', '--dry-run', dest='plan', action='store_true', help='Show packages plan (like a dry-run)', default=False)
    group_main.add_argument('--toolchain', dest='toolchain', help='Toolchain path (default is $ROOTDIR + "toolchain_default")', default=None)
    group_main.add_argument('--server', dest='server', help='artifact server', default=None)

    group_layer = group_main.add_mutually_exclusive_group()
    group_layer.add_argument('--layer', dest='priority', help='filter by layername. Valid values: (minimal|tools|third_party)', default=None)
    group_layer.add_argument('--no-layer', dest='no_priority', help='negation filter by layername. Valid values: (minimal|tools|third_party)', default=None)
    # group_main.add_argument('-t', '--tag', action='append', metavar='tag', type=str, help='NOT IMPLEMMENTED YET: filter tag third party')

    group_padawan = parser.add_argument_group('padawan')
    group_purge = group_padawan.add_mutually_exclusive_group()
    group_purge.add_argument('--no-purge', dest='no_purge', action='store_true', help='remove purge from pipeline', default=False)
    group_purge.add_argument('--only-purge', dest='only_purge', action='store_true', help='execute only purge in pipeline', default=False)

    group_prepare = group_padawan.add_mutually_exclusive_group()
    group_prepare.add_argument('--no-prepare', dest='no_prepare', action='store_true', help='remove prepare from pipeline', default=False)
    group_prepare.add_argument('--only-prepare', dest='only_prepare', action='store_true', help='execute only prepare in pipeline', default=False)
    group_compilation = group_padawan.add_mutually_exclusive_group()
    group_compilation.add_argument('--no-compilation', dest='no_compilation', action='store_true', help='remove compilation from pipeline', default=False)
    group_compilation.add_argument('--only-compilation', dest='only_compilation', action='store_true', help='execute only compilation in pipeline', default=False)
    group_packing = group_padawan.add_mutually_exclusive_group()
    group_packing.add_argument('--no-packing', dest='no_packing', action='store_true', help='remove packing from pipeline', default=False)
    group_packing.add_argument('--only-packing', dest='only_packing', action='store_true', help='execute only packing in pipeline', default=False)
    group_run_tests = group_padawan.add_mutually_exclusive_group()
    group_run_tests.add_argument('--no-run-tests', dest='no_run_tests', action='store_true', help='remove run_tests from pipeline', default=False)
    group_run_tests.add_argument('--only-run-tests', dest='only_run_tests', action='store_true', help='execute only run_tests in pipeline', default=False)
    group_upload = group_padawan.add_mutually_exclusive_group()
    group_upload.add_argument('--no-upload', dest='no_upload', action='store_true', help='remove upload from pipeline', default=False)
    group_upload.add_argument('--only-upload', dest='only_upload', action='store_true', help='execute only upload in pipeline', default=False)
    # creador de third parties
    group_jedi = parser.add_argument_group('jedi')
    group_jedi.add_argument('-o', '--only', dest='build_only', action='store_true', help='build only explicit packages and not your depends')
    group_jedi.add_argument('-v', '--verbose', action='count', help='verbose mode', default=0)
    group_jedi.add_argument('-q', '--quiet', dest='quiet', action='store_true', help='quiet mode', default=False)
    group_jedi.add_argument('-d', '--debug', action='store_true', help='Ridiculous debugging (probably not useful)')
    group_jedi.add_argument('--purge-if-fail', dest='purge_if_fail', action='store_true', help='purge even if a package finish with fail', default=False)
    group_jedi.add_argument('--toolchain-proposal', dest='toolchain_proposal', action='store_true', help='print automatic toolchain path', default=False)
    group_jedi.add_argument('--toolchain-proposal-basename', dest='toolchain_proposal_basename', action='store_true', help='print automatic toolchain basename path', default=False)
    group_jedi.add_argument('--with-svn', dest='with_svn', help='svn executable', default=None)
    group_jedi.add_argument('--fast', dest='fast', action='store_true', default=False, help=argparse.SUPPRESS)
    group_jedi.add_argument('--log', dest='log', help='specified full path log (default is "gtc.log")', default='gtc.log')
    group_jedi.add_argument('--no-packing-cmakefiles', action='store_true', dest='no_packing_cmakefiles', help='no packing cmakefiles', default=False)
    group_jedi.add_argument('--blacklist', dest='blacklist', help='third party in quarantine (default is $ROOTDIR + "blacklist.txt")', default=None)
    group_jedi.add_argument('--no-blacklist', action='append', dest='no_blacklist', help='list packages (separated with comma), for annular blacklist effect.', default=[])
    group_master_jedi = parser.add_argument_group('master jedi')
    group_master_jedi.add_argument('--rootdir', dest='rootdir', help='input folder with yamls, is recursive (default is current directory)', default=None)
    group_master_jedi.add_argument('--prefix', dest='prefix', help='output folder where packages will be generated (default is $TOOLCHAIN + "3rdparties")', default=None)
    group_master_jedi.add_argument('--cmakefiles', dest='cmakefiles', help='input folder with cmake scripts (default is $PREFIX + "cmakelib")', default=None)
    group_master_jedi.add_argument('--third-party-dir', dest='third_party_dir', help='output folder for cmakefiles (default is $CMAKEFILES + "3rdparty")', default=None)
    group_master_jedi.add_argument('--depends', dest='depends', help='json for save versions', default=None)
    parameters = parser.parse_args()

    toolchain_povided = parameters.toolchain is not None

    # parameters cmd line are paths
    parameters.rootdir = init_parameter_path(parameters.rootdir, os.getcwd())
    parameters.toolchain = init_parameter_path(parameters.toolchain, os.path.join(parameters.rootdir, 'output'))
    parameters.prefix = init_parameter_path(parameters.prefix, os.path.join(parameters.toolchain, '3rdparties'))
    parameters.cmakefiles = init_parameter_path(parameters.cmakefiles, os.path.join(parameters.prefix, 'cmaki'))
    parameters.third_party_dir = init_parameter_path(parameters.third_party_dir, os.path.join(parameters.cmakefiles, '3rdparty'))
    parameters.blacklist = init_parameter_path(parameters.blacklist, os.path.join(parameters.rootdir, 'blacklist.txt'))
    # parameters.depends = init_parameter_path(parameters.depends, os.path.join(parameters.cmakefiles, '..', 'depends.json'))

    # convert priority to int
    parameters.priority = convert_priority_to_integer(parameters.priority)
    parameters.no_priority = convert_priority_to_integer(parameters.no_priority)

    if(parameters.only_purge):
        parameters.no_purge = False
        parameters.no_prepare = True
        parameters.no_compilation = True
        parameters.no_packing = True
        parameters.no_run_tests = True
        parameters.no_upload = True
    elif(parameters.only_prepare):
        parameters.no_purge = True
        parameters.no_prepare = False
        parameters.no_compilation = True
        parameters.no_packing = True
        parameters.no_run_tests = True
        parameters.no_upload = True
    elif(parameters.only_compilation):
        parameters.no_purge = True
        parameters.no_prepare = True
        parameters.no_compilation = False
        parameters.no_packing = True
        parameters.no_run_tests = True
        parameters.no_upload = True
    elif(parameters.only_packing):
        parameters.no_purge = True
        parameters.no_prepare = True
        parameters.no_compilation = True
        parameters.no_packing = False
        parameters.no_run_tests = True
        parameters.no_upload = True
    elif(parameters.only_run_tests):
        parameters.no_purge = True
        parameters.no_prepare = True
        parameters.no_compilation = True
        parameters.no_packing = True
        parameters.no_run_tests = False
        parameters.no_upload = True
    elif(parameters.only_upload):
        parameters.no_purge = True
        parameters.no_prepare = True
        parameters.no_compilation = True
        parameters.no_packing = True
        parameters.no_run_tests = True
        parameters.no_upload = False

    # prepare logging
    if(parameters.debug):
        utils.setup_logging(logging.DEBUG, parameters.log)
    else:
        utils.setup_logging(logging.INFO, parameters.log)

    # if not set svn, use default
    if parameters.with_svn is None:
        if 'SUBVERSION' in os.environ:
            parameters.with_svn = os.environ['SUBVERSION']

    # generate toolchain prefix?
    if parameters.toolchain_proposal or parameters.toolchain_proposal_basename:
        if parameters.with_svn is not None:
            revision = utils.get_revision_svn(os.getcwd(), parameters.with_svn)
        else:
            revision = utils.get_revision_svn(os.getcwd())
        # set toolchain path
        if revision != -1:
            if parameters.toolchain_proposal_basename:
                parameters.toolchain = '%s.rev%d' % (datetime.datetime.now().strftime(image_pattern), revision)
            else:
                parameters.toolchain = os.path.join(os.environ['HOME_TOOLCHAIN'], '%s.rev%d' % (datetime.datetime.now().strftime(image_pattern), revision))
            logging.debug('Using toolchain prefix: %s' % parameters.toolchain)
        else:
            if parameters.with_svn is not None:
                logging.error('ERROR: svn not found in "%s"' % parameters.with_svn)
                logging.error('svn is optional, don\'t specify parameter --with-svn')
                sys.exit(1)
            if parameters.toolchain_proposal_basename:
                parameters.toolchain = '%s' % (datetime.datetime.now().strftime(image_pattern))
            else:
                parameters.toolchain = os.path.join(os.environ['HOME_TOOLCHAIN'], '%s' % (datetime.datetime.now().strftime(image_pattern)))
            logging.warning('No svn found, using toolchain prefix: %s' % parameters.toolchain)

        sys.stdout.write('%s\n' % parameters.toolchain)
        sys.stderr.write('You can use this in parameter --toolchain=%s\n' % parameters.toolchain)
        sys.exit(0)

    i = 0
    for package in parameters.packages:
        if package.startswith('github://'):
            repo = package[len('github://'):]
            utils.trymkdir('github')
            yml_file = os.path.join('github', '{}.yml'.format(repo.replace('/', '_')))
            if os.path.isfile(yml_file):
                utils.tryremove(yml_file)
            download_from_url('https://raw.githubusercontent.com/{}/master/cmaki.yml'.format(repo), yml_file)
            parameters.packages[i] = repo.split('/')[1]
        i += 1

    # set env TOOLCHAIN
    os.environ['TOOLCHAIN'] = parameters.toolchain

    # prepare cmakelin
    prepare_cmakelib(parameters)

    # generate amalgaimation yaml
    amalgamation_yaml(parameters.rootdir)

    # load yaml to python
    with open(yaml_collapsed_final, 'rt') as fy:
        third_parties_data_yaml = yaml.load(fy, Loader)

    # generate list of tuples (key, parameters)
    third_parties_data = []
    for third in third_parties_data_yaml['third_parties']:
        for key in third:
            parms = third[key]
            third_parties_data.append( (key, parms) )

    # create nodes and choose selected by filter and mask
    nodes = []
    selected = []
    for key, parms in third_parties_data:
        node = ThirdParty(parameters, key, parms)
        # define variables for unused projects
        package = node.get_package_name()

        # generate include scripts in toolchain
        if node.is_toolchain():
            node.generate_scripts_headers(compiler_replace_maps)

        # fill compiler_replace_maps
        node.apply_replace_maps(compiler_replace_maps)

        if (node.is_valid()
                and (parameters.priority is None or (parameters.priority == node.get_priority()))
                and (parameters.no_priority is None or (parameters.no_priority != node.get_priority()))):
            nodes.append( (key, node) )
            if (parameters.packages == ['.'] or parameters.packages == ['*']):
                selected.append( (key, node) )
            elif ((parameters.packages == ['all']) and (not node.get_exclude_from_all())):
                selected.append( (key, node) )
            else:
                for exp in parameters.packages:
                    if fnmatch.fnmatch(key.lower(), exp.lower()):
                        selected.append( (key, node) )

    # create relations
    for key, parms in third_parties_data:
        try:
            depends = parms['depends']
            mask = parms['mask']
            # depends valid
            valid = is_valid(key, mask)
            # depends blacklisted
            blacklisted = is_blacklisted(parameters.blacklist, parameters.no_blacklist, key)
            if (depends is not None) and valid and (not blacklisted):
                for depend in depends:
                    nodes_key = search_nodes_by_key(nodes, key)
                    nodes_depend = search_nodes_by_key(nodes, depend)
                    for nk in nodes_key:
                        for nd in nodes_depend:
                            nk.needs(nd)
        except KeyError:
            # no need create relations
            pass

    # 1/4: Generate solutions in each node
    solutions = []
    for key, select_node in selected:
        resolved = []
        if not parameters.build_only:
            select_node.resolver(resolved, [])
            solutions.append( resolved )
        else:
            solutions.append( [select_node] )

    # 2/4: clean subset
    groups = clean_subset(solutions)

    # 3/4: merge solutions with same root
    sols3 = {}
    for packages in groups:
        first = packages[0]
        if first not in sols3:
            sols3[first] = []
        chunk = sols3[first]
        for node in packages:
            if node != first:
                if node not in chunk:
                    chunk.append(node)

    # 4/4: write final plan
    groups = []
    for key, value in sols3.iteritems():
        newsolution = [key]
        for node in value:
            newsolution.append(node)
        groups.append(newsolution)

    # 2/4: clean subset
    groups = clean_subset(groups)

    # 5/4: sort groups
    groups_ordered = []
    for packages in groups:
        priority_total = 0
        for node in packages:
            priority_total += node.get_priority()
        priority_group = (priority_total / len(packages))
        groups_ordered.append( (priority_group, packages) )
    groups_ordered.sort(key=lambda tup: tup[0], reverse=False)

    # 6/4: validate groups
    for priority_total, packages in groups_ordered:
        if len(packages) > 0:
            priority_initial = packages[0].get_priority()
            for node in packages:
                if priority_initial != node.get_priority():
                    logging.error('[ERROR] You are mixing packages of different layers.')
                    logging.error('Invalid priority (%d) in package %s, expected %d:' % (node.get_priority(), node.get_package_name(), priority_initial))
                    logging.error('Any in group have bad depends:')
                    for node in packages:
                        sys.stdout.write('%s, ' % node.get_package_name())
                    sys.stdout.write('\n')
                    sys.exit(1)

    # show groups in --plan
    if len(groups_ordered) > 0:
        priority_prev = groups_ordered[0][0]
        i = 0
        for priority_total, packages in groups_ordered:
            if parameters.quiet:
                j = 0
                for node in packages:
                    sys.stdout.write("%s" % node.get_package_name())
                    if ((len(packages)-1) != j):
                        sys.stdout.write(" ")
                    j += 1
                sys.stdout.write('\n')
            else:
                if (priority_total > priority_prev) or (i == 0):
                    if priority_total in alias_priority_name:
                        layer_name = alias_priority_name[priority_total]
                    else:
                        layer_name = '%d' % priority_total
                    sys.stdout.write('\nLayer: %s\n\n' % layer_name)
                sys.stdout.write("\t[")
                j = 0
                for node in packages:
                    sys.stdout.write("%s" % node.get_package_name())
                    if ((len(packages)-1) != j):
                        sys.stdout.write(", ")
                    j += 1
                sys.stdout.write("]")
                sys.stdout.write('\n')

                priority_prev = priority_total
            i += 1
        sys.stdout.write('\n')
        sys.stdout.flush()
    else:
        logging.warning('No results.')
    # with --plan flag is like use --dry-run
    if parameters.plan:
        sys.exit(0)

    try:
        rets = OrderedDict()
        unittests = OrderedDict()
        skipping_if_priority_gt = 999
        announce_once = False
        #
        # pipeline: prepare, compile, packing, run_tests
        #
        for priority_group, packages in groups_ordered:

            if priority_group > skipping_if_priority_gt:
                if not announce_once:
                    logging.error("ignoring group because some previous group are failing:")
                    logging.warning('\tgroup is formed by:')
                    announce_once = True
                else:
                    logging.warning('')
                for node in packages:
                    logging.warning('    -- %s' % node.get_package_name())
                continue

            if len(packages) > 1:
                logging.info('--- Start group ---')
                for node in packages:
                    logging.info('- %s' % node.get_package_name())
                    # prepare include scripts
                    node.generate_scripts_headers(compiler_replace_maps)

            try:
                if (not parameters.no_purge):
                    run_purge(packages)

                # create pipeline
                p = pipeline.make_pipe()

                # feed third parties
                p = pipeline.feed(packages)(p)

                if (not parameters.no_prepare):
                    # download sources
                    p = pipeline.do(prepare, False, parameters, compiler_replace_maps)(p)

                if (not parameters.no_compilation):
                    # ./configure && make (configuration and compilation)
                    p = pipeline.do(compilation, False, parameters, compiler_replace_maps)(p)

                if (not parameters.no_packing):
                    # packing (generate .tar.gz)
                    p = pipeline.do(packing, False, parameters, compiler_replace_maps)(p)

                if (not parameters.no_run_tests):
                    # execute unittests and save results in "unittests"
                    p = pipeline.do(run_tests, False, parameters, compiler_replace_maps, unittests)(p)

                if (not parameters.no_upload):
                    # upload artifacts
                    p = pipeline.do(upload, False, parameters, compiler_replace_maps)(p)

                # save results in "rets"
                p = get_return_code(parameters, rets)(p)

                # close pipe
                pipeline.end_pipe()(p)

            except FailThirdParty as e:
                skipping_if_priority_gt = priority_group
                logging.error("stopping full group.")

            except exceptions_fail_group:
                logging.warning('Fatal exception in group:')
                for node in packages:
                    logging.warning('-- %s' % node.get_package_name())

            finally:
                # only purge when you are executing a full group
                if (not parameters.build_only) and (not parameters.no_purge):
                    if (parameters.purge_if_fail):
                        run_purge(packages)
                    else:
                        # purge only if all packages are ok
                        ret = 0
                        for node in packages:
                            ret += node.ret

                        if (ret == 0):
                            run_purge(packages)
                        else:
                            if len(packages) > 1:
                                logging.warning('Any in group is failing. No purge next group:')
                                for node in packages:
                                    logging.warning('    %s' % node.get_package_name())
                            else:
                                logging.warning('No purge %s because finished with fail' % node.get_package_name())

    except exceptions_fail_program:
        logging.warning('Force explicit exit ...')
    finally:
        ret = show_results(parameters, groups_ordered, rets, unittests)
        sys.exit(ret)

