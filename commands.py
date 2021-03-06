import tempfile
import getopt
import os, os.path
import sys
import shutil
import subprocess

try:
    from play.utils import isParentOf, copy_directory, replaceAll
    PLAY10 = False
except ImportError:
    PLAY10 = True

# GAE

MODULE = "gae"

COMMANDS = ["gae:deploy", "gae:package", "gae:update_indexes", "gae:vacuum_indexes", "gae:update_queues",
            "gae:update_dos", "gae:update_cron", "gae:cron_info", "gae:request_logs", "gae:rollback",
            "gae:update_backend", "gae:backend_info", "gae:update_dispatch"]
HELP = {
    'gae:deploy': "Deploy to Google App Engine",
    'gae:update_indexes': "Updating Indexes",
    'gae:vacuum_indexes': "Deleting Unused Indexes",
    'gae:update_queues': "Managing Task Queues",
    'gae:update_dos': "Managing DoS Protection",
    'gae:update_dispatch': "Managing Dispatch File",
    'gae:update_cron': "Managing Scheduled Tasks : upload cron job specifications",
    'gae:cron_info': "Managing Scheduled Tasks : verify your cron configuration",
    'gae:request_logs': "Download logs from Google App Engine",
    'gae:rollback': "Rollback last (failed) deployment",
    'gae:update_backend': "Managing Backend Instances : update your backend configuration",
    'gae:backend_info': "Managing Backend Instances : verify your backend configuration"
}


def find(f, seq):
  """Return first item in sequence where f(item) == True."""
  for item in seq:
    if f(item):
      return item

def package_as_gae_war(app, env, war_path, war_zip_path, war_exclusion_list = None):
    if war_exclusion_list is None:
        war_exclusion_list = []
    app.check()
    modules = app.modules()
    classpath = app.getClasspath()

    if not war_path:
        print "~ Oops. Please specify a path where to generate the WAR, using the -o or --output option"
        print "~"
        sys.exit(-1)

    if os.path.exists(war_path) and not os.path.exists(os.path.join(war_path, 'WEB-INF')) and not os.path.exists(os.path.join(war_path, 'META-INF')):
        print "~ Oops. The destination path already exists but does not seem to host a valid WAR structure", war_path
        print "~"
        sys.exit(-1)

    if isParentOf(app.path, war_path):
        print "~ Oops. Please specify a destination directory outside of the application"
        print "~"
        sys.exit(-1)

    print "~ Packaging current version of the framework and the application to %s ..." % (os.path.normpath(war_path))
    if os.path.exists(war_path): shutil.rmtree(war_path)
    if os.path.exists(os.path.join(app.path, 'war')):
        copy_directory(os.path.join(app.path, 'war'), war_path)
    else:
        os.makedirs(war_path)

    def process_module(module_path):
        def path(f):
            return os.path.join(module_path, f)
        def exists(f):
            return os.path.exists(path(f))
        def mkdir(f):
            os.mkdir(path(f))
        def rmtree(f):
            shutil.rmtree(path(f))
        def mkdir_if_not_exists(f):
            if not exists(f):
                mkdir(f)
        def rm_if_exists(f):
            if exists(f):
                rmtree(f)

        print '~ Processing GAE module in', module_path
        if not exists('WEB-INF'):
            mkdir('WEB-INF')

        if not exists('WEB-INF/web.xml'):
            shutil.copyfile(os.path.join(env["basedir"], 'resources/war/web.xml'), path('WEB-INF/web.xml'))

        # Replacements
        application_name = app.readConf('application.name')
        replaceAll(path('WEB-INF/web.xml'), r'%APPLICATION_NAME%', application_name)
        if env["id"]:
            replaceAll(path('WEB-INF/web.xml'), r'%PLAY_ID%', env["id"])
        else:
            replaceAll(path('WEB-INF/web.xml'), r'%PLAY_ID%', 'war')

        rm_if_exists('WEB-INF/application')

        copy_directory(app.path, path('WEB-INF/application'), war_exclusion_list)

        for f in ['WEB-INF/application/war',
                'WEB-INF/application/logs',
                'WEB-INF/application/tmp',
                'WEB-INF/application/lib',
                'WEB-INF/application/modules']:
            rm_if_exists(f)

        copy_directory(os.path.join(app.path, 'conf'), path('WEB-INF/classes'))
        copy_directory(os.path.join(app.path, 'public'), path('WEB-INF/public'))
        rm_if_exists('WEB-INF/lib')
        mkdir('WEB-INF/lib')
        for jar in classpath:
            # SPECIFIC GAE : excludes from the libs all provided and postgres/mysql/jdbc libs
            # keeps appengine-api only
            # appengine-api-labs removed
            gae_excluded = ['provided-', 'postgres', 'mysql', 'jdbc',
                            'appengine-agent',  'appengine-agentimpl',
                            'appengine-agentruntime', 'appengine-api-stubs',
                            'appengine-local-runtime', 'appengine-testing']
            if jar.endswith('.jar'):
                if find(lambda excl: excl in jar, gae_excluded):
                    print "~ Excluding JAR %s ..." % jar
                else:
                    shutil.copyfile(jar, path('WEB-INF/lib/%s' % os.path.split(jar)[1]))
        rm_if_exists('WEB-INF/framework')
        mkdir('WEB-INF/framework')
        copy_directory(os.path.join(env["basedir"], 'framework/templates'), path('WEB-INF/framework/templates'))

        # modules
        for module in modules:
            to = path('WEB-INF/application/modules/%s' % os.path.basename(module))
            copy_directory(module, to)
            for f in ['src', 'src', 'dist', 'dist', 'samples-and-tests', 'samples-and-tests',
                    'build.xml', 'build.xml', 'commands.py', 'commands.py', 'lib', 'lib',
                    'nbproject', 'nbproject', 'documentation', 'documentation']:
                f = os.path.join(to, f)
                if os.path.exists(f):
                    if os.path.isfile(f):
                        os.remove(f)
                    else:
                        shutil.rmtree(f)

        mkdir_if_not_exists('WEB-INF/resources')
        shutil.copyfile(os.path.join(env["basedir"], 'resources/messages'), path('WEB-INF/resources/messages'))

    gae_modules = app.readConf('gae.modules')
    if gae_modules:
        print '~ GAE Modules:', gae_modules
    gae_modules = gae_modules.split(',') if gae_modules else ['.']

    for gae_module in gae_modules:
        process_module(os.path.join(war_path, gae_module))

    if war_zip_path:
        print "~ Creating zipped archive to %s ..." % (os.path.normpath(war_zip_path))
        if os.path.exists(war_zip_path):
            os.remove(war_zip_path)
        zip = zipfile.ZipFile(war_zip_path, 'w', zipfile.ZIP_STORED)
        dist_dir = os.path.join(app.path, 'dist')
        for (dirpath, dirnames, filenames) in os.walk(war_path):
            if dirpath == dist_dir:
                continue
            if dirpath.find('/.') > -1:
                continue
            for file in filenames:
                if file.find('~') > -1 or file.startswith('.'):
                    continue
                zip.write(os.path.join(dirpath, file), os.path.join(dirpath[len(war_path):], file))

        zip.close()

def execute(**kargs):
    command = kargs.get("command")
    app = kargs.get("app")
    args = kargs.get("args")
    env = kargs.get("env")

    username = ""
    password = ""

    gae_path = None
    war_path = os.path.join(tempfile.gettempdir(), '%s.war' % os.path.basename(app.path))

    try:
        optlist, args2 = getopt.getopt(args, '', ['gae=', 'username=', 'password='])
        for o, a in optlist:
            if o == '--gae':
                gae_path = os.path.normpath(os.path.abspath(a))

    except getopt.GetoptError, err:
        print "~ %s" % str(err)
        print "~ "
        sys.exit(-1)

    if not gae_path and os.environ.has_key('GAE_PATH'):
        gae_path = os.path.normpath(os.path.abspath(os.environ['GAE_PATH']))

    if not gae_path:
        print "~ You need to specify the path of you GAE installation, "
        print "~ either using the $GAE_PATH environment variable or with the --gae option"
        print "~ "
        sys.exit(-1)

    # check
    if not os.path.exists(os.path.join(gae_path, 'bin/appcfg.sh')):
        print "~ %s seems not to be a valid GAE installation (checked for bin/appcfg.sh)" % gae_path
        print "~ This module has been tested with GAE 1.5.0"
        print "~ "
        sys.exit(-1)

    itemsToRemove = []
    for a in args:
        if a.find('--gae') == 0:
            itemsToRemove.insert(0, a)

        if a.find('--username=') != -1:
            itemsToRemove.insert(0, a)
            username = a[11:]

        if a.find('--password=') != -1:
            itemsToRemove.insert(0, a)
            password = a[11:]

    for item in itemsToRemove:
        args.remove(item)


    if command == "gae:deploy":
        print '~'
        print '~ Compiling'
        print '~ ---------'

        remaining_args = []
        app.check()
        java_cmd = app.java_cmd(args)
        if os.path.exists(os.path.join(app.path, 'tmp')):
            shutil.rmtree(os.path.join(app.path, 'tmp'))
        if os.path.exists(os.path.join(app.path, 'precompiled')):
            shutil.rmtree(os.path.join(app.path, 'precompiled'))
        java_cmd.insert(2, '-Dprecompile=yes')
        try:
            result = subprocess.call(java_cmd, env=os.environ)
            if not result == 0:
                print "~"
                print "~ Precompilation has failed, stop deploying."
                print "~"
                sys.exit(-1)

        except OSError:
            print "Could not execute the java executable, please make sure the JAVA_HOME environment variable is set properly (the java executable should reside at JAVA_HOME/bin/java). "
            sys.exit(-1)

        if os.path.exists(os.path.join(app.path, 'tmp')):
            shutil.rmtree(os.path.join(app.path, 'tmp'))

        print '~'
        print '~ Packaging'
        print '~ ---------'

        package_as_gae_war(app, env, war_path, None, ['submodules'])



        print '~'
        print '~ Deploying'
        print '~ ---------'

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin update %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 update %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin update %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 update %s' % (gae_path, war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:package":
        print '~'
        print '~ Compiling'
        print '~ ---------'

        remaining_args = []
        app.check()
        java_cmd = app.java_cmd(args)
        if os.path.exists(os.path.join(app.path, 'tmp')):
            shutil.rmtree(os.path.join(app.path, 'tmp'))
        if os.path.exists(os.path.join(app.path, 'precompiled')):
            shutil.rmtree(os.path.join(app.path, 'precompiled'))
        java_cmd.insert(2, '-Dprecompile=yes')
        try:
            result = subprocess.call(java_cmd, env=os.environ)
            if not result == 0:
                print "~"
                print "~ Precompilation has failed, stop deploying."
                print "~"
                sys.exit(-1)

        except OSError:
            print "Could not execute the java executable, please make sure the JAVA_HOME environment variable is set properly (the java executable should reside at JAVA_HOME/bin/java). "
            sys.exit(-1)

        if os.path.exists(os.path.join(app.path, 'tmp')):
            shutil.rmtree(os.path.join(app.path, 'tmp'))

        print '~'
        print '~ Packaging'
        print '~ ---------'

        package_as_gae_war(app, env, war_path, None, ['submodules'])
        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:update_dispatch":
        print '~'
        print '~ Updating dispatch file'
        print '~ ---------'

        default_module = os.path.join(war_path, 'default')
        if os.path.exists(default_module):
            war_path = default_module

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin update_dispatch %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 update_dispatch %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin update_dispatch %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 update_dispatch %s' % (gae_path, war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:update_indexes":
        print '~'
        print '~ Updating indexes'
        print '~ ---------'

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin update_indexes %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 update_indexes %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin update_indexes %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 update_indexes %s' % (gae_path, war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:vacuum_indexes":
        print '~'
        print '~ Deleting Unused Indexes'
        print '~ ---------'

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin vacuum_indexes %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 vacuum_indexes %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin vacuum_indexes %s' % (password, gae_path, username, war_path))
            else:
                 os.system('%s/bin/appcfg.sh --oauth2 vacuum_indexes %s' % (gae_path, war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:update_queues":
        print '~'
        print '~ Updating Task Queues'
        print '~ ---------'

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin update_queues %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 update_queues %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin update_queues %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 update_queues %s' % (gae_path, war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:update_dos":
        print '~'
        print '~ Updating DoS Protection'
        print '~ ---------'

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin update_dos %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 update_dos %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin update_dos %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 update_dos %s' % (gae_path, war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:update_cron":
        print '~'
        print '~ Updating cron job specifications'
        print '~ ---------'

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin update_cron %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 update_cron %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin update_cron %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 update_cron %s' % (gae_path, war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:request_logs":
        print '~'
        print '~ Downloading Logs'
        print '~ ---------'

        if os.name == 'nt':
            os.system('%s/bin/appcfg.cmd %s request_logs %s ./logs/production.log' % (gae_path, ' '.join(args2), war_path))
        else:
            os.system('%s/bin/appcfg.sh %s request_logs %s ./logs/production.log' % (gae_path, ' '.join(args2), war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:rollback":
        print '~'
        print '~ Performing rollback'
        print '~ ---------'

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin rollback %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 rollback %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin rollback %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 rollback %s' % (gae_path, war_path))

        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:update_backend":
        print '~'
        print '~ Updating backend specifications'
        print '~ ---------'

        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin backends update %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 backends update %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin backends update %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 backends update %s' % (gae_path, war_path))
        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
    if command == "gae:backend_info":
        print '~'
        print '~ Listing backend specifications'
        print '~ ---------'
        if os.name == 'nt':
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.cmd --email=%s --passin backends list %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.cmd --oauth2 backends list %s' % (gae_path, war_path))
        else:
            if (username != "" and password != ""):
                os.system('echo %s | %s/bin/appcfg.sh --email=%s --passin backends list %s' % (password, gae_path, username, war_path))
            else:
                os.system('%s/bin/appcfg.sh --oauth2 backends list %s' % (gae_path, war_path))
        print "~ "
        print "~ Done!"
        print "~ "
        sys.exit(0)
