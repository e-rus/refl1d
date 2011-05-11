import time
import threading
import wx
import wx.lib.newevent

from copy import deepcopy
from threading import Thread
from ..mystic import monitor
from ..fitters import FitDriver
from ..mapper import  MPMapper, SerialMapper

from .convergence_view import ConvergenceMonitor
#==============================================================================

PROGRESS_DELAY = 5
IMPROVEMENT_DELAY = 5

(FitProgressEvent, EVT_FIT_PROGRESS) = wx.lib.newevent.NewEvent()
(FitCompleteEvent, EVT_FIT_COMPLETE) = wx.lib.newevent.NewEvent()

# NOTE: GUI monitors are running in a separate thread.  They should not
# touch the problem internals.
class GUIProgressMonitor(monitor.TimedUpdate):
    def __init__(self, win, problem, progress=None, improvement=None):
        monitor.TimedUpdate.__init__(self, progress=progress or PROGRESS_DELAY,
                                     improvement=improvement or IMPROVEMENT_DELAY)
        self.win = win
        self.problem = problem

    def show_progress(self, history):
        evt = FitProgressEvent(problem=self.problem,
                               message="progress",
                               step=history.step[0],
                               value=history.value[0],
                               point=history.point[0]+0) # avoid race
        wx.PostEvent(self.win, evt)

    def show_improvement(self, history):
        evt = FitProgressEvent(problem=self.problem,
                               message="improvement",
                               step=history.step[0],
                               value=history.value[0],
                               point=history.point[0]+0) # avoid race
        wx.PostEvent(self.win, evt)


class GUIMonitor(monitor.Monitor):
    """
    Generic GUI monitor.

    Sends a fit progress event messge, **monitor.progress() every n seconds.
    """
    def __init__(self, win, problem, message, monitor, rate=None):
        self.time = 0
        self.rate = rate or 10
        self.win = win
        self.problem = problem
        self.message = message
        self.monitor = monitor
    def config_history(self, history):
        self.monitor.config_history(history)
        history.requires(time=1)
    def __call__(self, history):
        self.monitor(history)
        if history.time[0] >= self.time+self.rate:
            evt = FitProgressEvent(problem=self.problem,
                                   message=self.message,
                                   **self.monitor.progress())
            wx.PostEvent(self.win, evt)
            self.time = history.time[0]
    def final(self):
        """
        Close out the monitor
        """
        evt = FitProgressEvent(problem=self.problem,
                               message=self.message,
                               **self.monitor.progress())
        wx.PostEvent(self.win, evt)

# Horrible hack: we put the DREAM state in the fitter object the first time
# back from the DREAM monitor; if our fitter object contains dream_state,
# then we will send the dream_update notifiction periodically.
class DreamMonitor(monitor.Monitor):
    def __init__(self, win, problem, message, fitter, rate=None):
        self.time = 0
        self.rate = rate or 60
        self.win = win
        self.problem = problem
        self.fitter = fitter
        self.message = message
        self.state = None
    def config_history(self, history):
        history.requires(time=1)
    def __call__(self, history):
        self.state = history.uncertainty_state
        if history.time[0] >= self.time+self.rate \
            and hasattr(history, 'uncertainty_state'):
            # Gack! holding on to state for final
            evt = FitProgressEvent(problem=self.problem,
                                   message="uncertainty_update",
                                   state = deepcopy(self.state))
            wx.PostEvent(self.win, evt)
            self.time = history.time[0]
    def final(self):
        """
        Close out the monitor
        """
        if self.state:
            evt = FitProgressEvent(problem=self.problem,
                                   message="uncertainty_update",
                                   state = deepcopy(self.state))
            wx.PostEvent(self.win, evt)



#==============================================================================

class FitThread(Thread):
    """Run the fit in a separate thread from the GUI thread."""
    def __init__(self, win, problem=None,
                 fitclass=None, options=None, mapper=None):
        # base class initialization
        #Process.__init__(self)

        Thread.__init__(self)
        self.win = win
        self.problem = problem
        self.fitclass = fitclass
        self.options = options
        self.mapper = mapper
        self.start() # Start it working.

    def run(self):
        # TODO: we have no interlocks on changes in problem state.  What
        # happens when the user changes the problem while a fit is being run?
        # May want to keep a history of changes to the problem definition,
        # along with a function to reverse them so we can handle undo.

        # NOTE: Problem must be the original problem (not a copy) when used
        # inside the GUI monitor otherwise AppPanel will not be able to
        # recognize that it is the same problem when updating views.
        monitors = [GUIProgressMonitor(self.win, self.problem),
                    GUIMonitor(self.win, self.problem,
                               message="convergence_update",
                               monitor=ConvergenceMonitor(),
                               rate=5),
                    DreamMonitor(self.win, self.problem,
                                 fitter = self.fitclass,
                                 message="uncertainty_update",
                                 rate=15),
                    ]
        if True: # Multiprocessing parallel
            mapper = MPMapper
        else:
            mapper = SerialMapper

        # Be safe and keep a private copy of the problem while fitting
        #print "fitclass",self.fitclass
        problem = deepcopy(self.problem)
        #print "fitclass id",id(self.fitclass),self.fitclass,threading.current_thread()
        driver = FitDriver(self.fitclass, problem=problem,
                           monitors=monitors,
                           mapper = mapper.start_mapper(problem, []),
                           **self.options)

        x,fx = driver.fit()
        # Give final state message from monitors
        for M in monitors:
            if hasattr(M, 'final'): M.final()
        evt = FitCompleteEvent(problem=self.problem,
                               point=x,
                               value=fx)
        wx.PostEvent(self.win, evt)
