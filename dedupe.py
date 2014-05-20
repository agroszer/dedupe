import logging
import optparse
import os
import shutil
import sys
import tempfile

from collections import defaultdict
from hashlib import sha1

BLOCKSIZE = 65536

LOGGER = logging.getLogger('')

parser = optparse.OptionParser(
    usage='dedupe source repository',
    description='Deduplicate files by replacing them with symlinks')

parser.add_option('-v', '--verbose', dest='verbose', action='count',
                  default=0,
                  help='Be more verbose (can be repeated)')

parser.add_option('-l', '--log', dest='logfile',
                  default=None,
                  help=(u'Specify a log file to write'))

parser.add_option('-s', '--save', dest='save_backlinks',
                  default=None,
                  help=(u'Save backlinks to repo root'))

parser.add_option('-m', '--move', dest='use_move',
                  default=None,
                  help=(u'Try move instead of copy when adding to repo'))

parser.add_option('--tests', dest='run_tests', default=False,
                  action='store_true',
                  help='Run tests')


def compare(have, want):
    if have != want:
        print "want:"
        print want
        print "have:"
        print have


def run_test(srcfolder, repofolder, useMove):
    # add files
    def wrt(fn, content):
        fname = os.path.join(srcfolder, fn)
        dirname = os.path.dirname(fname)
        makedirs(dirname)
        with open(fname, 'wb') as f:
            f.write(content)

    # fe05bcdcdc4928012781a5f1a2a77cbb5398e106
    wrt('one.txt', 'one')
    # ad782ecdac770fc6eb9a62e44f90873fb97fb26b
    wrt('two.txt', 'two')
    wrt('dupeone.txt', 'one')

    repo = Repo(repofolder)
    counter = defaultdict(int)
    dedupe(srcfolder, repo, counter, useMove=useMove)
    repo.saveBacklinks()

    # check
    def rd(fn):
        fname = os.path.join(srcfolder, fn)
        with open(fname, 'rb') as f:
            return f.read()

    def islnk(fn):
        fname = os.path.join(srcfolder, fn)
        return os.path.islink(fname)

    def check1():
        assert rd('one.txt') == 'one'
        assert rd('two.txt') == 'two'
        assert rd('dupeone.txt') == 'one'
        assert islnk('one.txt')
        assert islnk('two.txt')
        assert islnk('dupeone.txt')

        assert repo.hasHash('fe05bcdcdc4928012781a5f1a2a77cbb5398e106')
        assert repo.hasHash('ad782ecdac770fc6eb9a62e44f90873fb97fb26b')
    check1()

    compare(counter, {'dup': 1, 'new': 2, 'all': 3})

    # another run
    wrt('fld/another_two.txt', 'two')
    # b802f384302cb24fbab0a44997e820bf2e8507bb
    wrt('fld/three.txt', 'three')

    counter = defaultdict(int)
    dedupe(srcfolder, repo, counter, useMove=useMove)
    repo.saveBacklinks()

    def check2():
        assert rd('fld/another_two.txt') == 'two'
        assert rd('fld/three.txt') == 'three'

        repo = Repo(repofolder)
        assert repo.hasHash('b802f384302cb24fbab0a44997e820bf2e8507bb')

    check1()
    check2()
    compare(counter, {'dup': 1, 'new': 1, 'all': 5, 'already': 3})

    back = os.path.join(repofolder, 'backlinks.txt')
    c = open(back, 'r').read()
    c = c.replace(srcfolder, 'src')
    compare(c, """ad782ecdac770fc6eb9a62e44f90873fb97fb26b
 src/fld/another_two.txt
 src/two.txt
b802f384302cb24fbab0a44997e820bf2e8507bb
 src/fld/three.txt
fe05bcdcdc4928012781a5f1a2a77cbb5398e106
 src/dupeone.txt
 src/one.txt
""")

    fwd = os.path.join(repofolder, 'fwdlinks.txt')
    c = open(fwd, 'r').read()
    c = c.replace(srcfolder, 'src')
    compare(c, """src/dupeone.txt
 fe05bcdcdc4928012781a5f1a2a77cbb5398e106
src/fld/another_two.txt
 ad782ecdac770fc6eb9a62e44f90873fb97fb26b
src/fld/three.txt
 b802f384302cb24fbab0a44997e820bf2e8507bb
src/one.txt
 fe05bcdcdc4928012781a5f1a2a77cbb5398e106
src/two.txt
 ad782ecdac770fc6eb9a62e44f90873fb97fb26b
""")


def run_tests():
    srcfolder = tempfile.mkdtemp(prefix='tmp-dedupe-')
    repofolder = tempfile.mkdtemp(prefix='tmp-dedupe-')

    run_test(srcfolder, repofolder, False)

    shutil.rmtree(srcfolder)
    shutil.rmtree(repofolder)

    srcfolder = tempfile.mkdtemp(prefix='tmp-dedupe-')
    repofolder = tempfile.mkdtemp(prefix='tmp-dedupe-')

    run_test(srcfolder, repofolder, True)

    shutil.rmtree(srcfolder)
    shutil.rmtree(repofolder)


def makedirs(dirname):
    try:
        os.makedirs(dirname)
    except OSError:
        pass


class Repo(object):
    def __init__(self, folder, useMove=False):
        self.folder = folder
        self.backlinks = defaultdict(set)
        self.useMove = useMove
        self.longest = 0

    def hash_to_filename(self, hsh):
        fname = os.path.join(self.folder, hsh[:2], hsh[2:4], hsh[4:6], hsh)
        return fname

    def filename_to_hash(self, fname):
        return os.path.basename(fname)

    def hasHash(self, hsh):
        return os.path.exists(self.hash_to_filename(hsh))

    def addFile(self, fullfname, hsh):
        tgtfname = self.hash_to_filename(hsh)
        dirname = os.path.dirname(tgtfname)
        makedirs(dirname)
        if self.useMove:
            try:
                os.rename(fullfname, tgtfname)
            except OSError:
                shutil.copyfile(fullfname, tgtfname)
        else:
            shutil.copyfile(fullfname, tgtfname)
        return tgtfname

    def remember(self, hsh, tgtfname):
        self.backlinks[hsh].add(tgtfname)

    def saveBacklinks(self):
        fwdlinks = defaultdict(list)
        back = os.path.join(self.folder, 'backlinks.txt')
        with open(back, 'w') as f:
            for hsh in sorted(self.backlinks.keys()):
                f.write(hsh+'\n')
                for tgt in sorted(self.backlinks[hsh]):
                    f.write(' '+tgt+'\n')
                    fwdlinks[tgt].append(hsh)
        fwd = os.path.join(self.folder, 'fwdlinks.txt')
        with open(fwd, 'w') as f:
            for fname in sorted(fwdlinks.keys()):
                f.write(fname+'\n')
                for hsh in sorted(fwdlinks[fname]):
                    f.write(' '+hsh+'\n')


def getHash(fname):
    LOGGER.debug('Calculating hash for %s', fname)
    hasher = sha1()
    with open(fname, 'rb') as afile:
        buf = afile.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = afile.read(BLOCKSIZE)
    return hasher.hexdigest()


def dedupe(srcfolder, repo, counter, useMove=False):
    for root, dirs, files in os.walk(srcfolder):
        LOGGER.debug("Processing folder %s", root)
        for fname in files:
            fullfname = os.path.join(root, fname)
            try:
                if os.path.islink(fullfname):
                    tgt = os.path.realpath(fullfname)
                    hsh = repo.filename_to_hash(tgt)
                    if repo.hasHash(hsh):
                        counter['already'] += 1
                        LOGGER.debug('%s is already linked to %s', fullfname, tgt)
                        repo.remember(hsh, fullfname)
                    else:
                        counter['missing'] += 1
                        LOGGER.warn('%s linked to %s, target is MISSING!',
                                    fullfname, tgt)
                else:
                    hsh = getHash(fullfname)
                    if repo.hasHash(hsh):
                        counter['dup'] += 1
                        LOGGER.debug('adding %s to repo, hash %s already exists',
                                     fullfname, hsh)
                        tgtfname = repo.hash_to_filename(hsh)
                    else:
                        counter['new'] += 1
                        LOGGER.debug('adding %s to repo with hash %s',
                                     fullfname, hsh)
                        tgtfname = repo.addFile(fullfname, hsh)
                    os.remove(fullfname)
                    os.symlink(tgtfname, fullfname)
                    repo.remember(hsh, fullfname)
                counter['all'] += 1
            except OSError:
                LOGGER.exception('Failed on %s', fullfname)


def main(argv=sys.argv[1:]):
    opts, args = parser.parse_args(argv)

    if opts.run_tests:
        run_tests()
        return

    if not args:
        parser.error('Please specify a source and repository.')

    soh = logging.StreamHandler(sys.stdout)
    soh.setLevel(logging.DEBUG if opts.verbose else logging.INFO)
    LOGGER.setLevel(logging.DEBUG if opts.verbose else logging.INFO)
    LOGGER.addHandler(soh)

    if opts.logfile:
        fh = logging.FileHandler(opts.logfile)
        fh.setLevel(logging.DEBUG if opts.verbose else logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        LOGGER.setLevel(logging.DEBUG if opts.verbose else logging.INFO)
        LOGGER.addHandler(fh)

    try:
        counter = defaultdict(int)
        repofolder = args[1]
        repo = Repo(repofolder)

        srcfolder = args[0]
        if srcfolder.startswith('@'):
            srcfolder = srcfolder[1:]
            with open(srcfolder, 'r') as f:
                folders = [line.strip() for line in f.readlines()]
                folders = [line for line in folders if line]
        else:
            folders = [srcfolder]
        for folder in folders:
            LOGGER.info("starting with dedupe of %s to %s", folder, repofolder)

            dedupe(folder, repo, counter,
                   useMove=opts.use_move)

            LOGGER.info("done with dedupe of %s to %s", folder, repofolder)

        if opts.save_backlinks:
            LOGGER.debug("saving backlinks")
            repo.saveBacklinks()

        LOGGER.info("Stats:")
        LOGGER.info("All files: %s", counter['all'])
        LOGGER.info("Already linked files: %s", counter['already'])
        LOGGER.info("Missing files: %s", counter['missing'])
        LOGGER.info("Dup files: %s", counter['dup'])
        LOGGER.info("New files: %s", counter['new'])
    except:
        LOGGER.exception("FAILED")
        sys.exit(1)


if __name__ == '__main__':
    main()
