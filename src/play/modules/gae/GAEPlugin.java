package play.modules.gae;

import com.google.apphosting.api.ApiProxy;
import play.Logger;
import play.Play;
import play.PlayPlugin;
import play.cache.Cache;
import play.libs.IO;
import play.libs.Mail;
import play.mvc.Router;

import javax.mail.Session;
import java.io.File;
import java.util.Properties;

public class GAEPlugin extends PlayPlugin {

    public PlayDevEnvironment devEnvironment = null;
    public boolean prodGAE;

    @Override
    public void onLoad() {
        // Remove Jobs from plugin list iff NOT running tests
        // Jobs plugin is necessary to dispatch test executions
        if (! Play.runingInTestMode()) {
            Play.pluginCollection.disablePlugin(play.jobs.JobsPlugin.class);
        }
    	
        // Create a fake development environment if not run in the Google SDK
        if (ApiProxy.getCurrentEnvironment() == null) {
            Logger.warn("");
            Logger.warn("Google App Engine module");
            Logger.warn("~~~~~~~~~~~~~~~~~~~~~~~");
            Logger.warn("No Google App Engine environment found. Setting up a development environment");
            devEnvironment = PlayDevEnvironment.create();
            System.setProperty("appengine.orm.disable.duplicate.emf.exception", "yes");
            Logger.warn("");
        } else {
            // Force to PROD mode when hosted on production GAE
            Play.mode = Play.Mode.PROD;
            prodGAE = true;
        }
    }

    @Override
    public void onRoutesLoaded() {
        if(Play.mode == Play.Mode.DEV) {
            Router.addRoute("GET", "/_ah/login", "GAEActions.login");
            Router.addRoute("POST", "/_ah/login", "GAEActions.doLogin");
            Router.addRoute("GET", "/_ah/logout", "GAEActions.logout");
            Router.addRoute("GET", "/_ah/start", "GAEActions.startBackend");
            Router.addRoute("GET", "/_ah/admin", "GAEActions.adminConsole");
        }
    }

    @Override
    public void onApplicationStart() {
        // Wrap the GAE cache
        if (devEnvironment == null) {
            Cache.forcedCacheImpl = new GAECache(); 
        }

        // Provide the correct JavaMail session
        Mail.session = Session.getDefaultInstance(new Properties(), null);
        Mail.asynchronousSend = false;
    }
    
    @Override
    public void beforeInvocation() {
        // Set the current development environment if needed
        if (devEnvironment != null) {
            ApiProxy.setEnvironmentForCurrentThread(new PlayDevEnvironment());
        }
    }

    @Override
    public void onConfigurationRead() {
        if (devEnvironment == null) {
            Play.configuration.remove("smtp.mock");
            Play.configuration.setProperty("application.log", "DEBUG");
        }
        Play.configuration.setProperty("webservice", "urlfetch");
        Play.configuration.setProperty("upload.threshold", Integer.MAX_VALUE + "");
    }
}
