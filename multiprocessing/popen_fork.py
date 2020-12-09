import os
import sys
import signal

import uuid

from . import util

__all__ = ['Popen']

#
# Start child process using fork
#

class Popen(object):
    method = 'fork'

    def __init__(self, process_obj):
        util._flush_std_streams()
        self.returncode = None
        self.finalizer = None
        self._launch(process_obj)

    def duplicate_for_child(self, fd):
        return fd

    def poll(self, flag=os.WNOHANG):
        if self.returncode is None:
            try:
                pid, sts = os.waitpid(self.pid, flag)
            except OSError as e:
                # Child process not yet created. See #1731717
                # e.errno == errno.ECHILD == 10
                return None
            if pid == self.pid:
                if os.WIFSIGNALED(sts):
                    self.returncode = -os.WTERMSIG(sts)
                else:
                    assert os.WIFEXITED(sts), "Status is {:n}".format(sts)
                    self.returncode = os.WEXITSTATUS(sts)
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            if timeout is not None:
                from multiprocessing.connection import wait
                if not wait([self.sentinel], timeout):
                    return None
            # This shouldn't block if wait() returned successfully.
            return self.poll(os.WNOHANG if timeout == 0.0 else 0)
        return self.returncode

    def _send_signal(self, sig):
        if self.returncode is None:
            try:
                os.kill(self.pid, sig)
            except ProcessLookupError:
                pass
            except OSError:
                if self.wait(timeout=0.1) is None:
                    raise

    def terminate(self):
        self._send_signal(signal.SIGTERM)

    def kill(self):
        self._send_signal(signal.SIGKILL)

    def _launch(self, process_obj):

        if os.environ.get("SCOREP_PYTHON_BINDINGS_INITIALISED") == "true":
            # use scorep only if current process also uses scorep
            # SCOREP_PYTHON_BINDINGS_INITIALISED is set by scorep-bindings-python
            scorep_exp_base = os.environ['SCOREP_EXPERIMENT_DIRECTORY'] if "SCOREP_EXPERIMENT_DIRECTORY" in os.environ else "scorep"
            os.environ['SCOREP_EXPERIMENT_DIRECTORY'] = scorep_exp_base + "_" + uuid.uuid4().hex


        code = 1
        parent_r, child_w = os.pipe()
        self.pid = os.fork()
        if self.pid == 0:
            try:
                os.close(parent_r)
                code = process_obj._bootstrap()
            finally:
                os._exit(code)
        else:
            os.close(child_w)
            self.finalizer = util.Finalize(self, os.close, (parent_r,))
            self.sentinel = parent_r

    def close(self):
        if self.finalizer is not None:
            self.finalizer()
