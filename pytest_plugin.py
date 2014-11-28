"""
pytest ipython plugin modification

Authors: D. Cortes, O. Laslett

For now, install pytest-ipynb plugin (
https://github.com/zonca/pytest-ipynb ) :

    sudo pip install pytest-ipynb

And replace the file with:

    sudo cp pytest_plugin.py /usr/local/lib/python2.7/dist-packages/pytest_ipynb/plugin.py

"""

import pytest
import os
import sys
# For regular expressions:
import re

try:
    from exceptions import Exception
except:
    pass

wrapped_stdin = sys.stdin
sys.stdin = sys.__stdin__
from IPython.kernel import KernelManager
sys.stdin = wrapped_stdin
try:
    from Queue import Empty
except:
    from queue import Empty

from IPython.nbformat.current import reads, NotebookNode


# Colours for outputs
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


class IPyNbException(Exception):
    """ custom exception for error reporting. """


def pytest_collect_file(path, parent):
    """
    Collect iPython notebooks using the specified pytest hook
    """
    if path.fnmatch("*.ipynb"):
        return IPyNbFile(path, parent)


def get_cell_description(cell_input):
    """
    Gets cell description

    Cell description is the first line of a cell,
    in one of this formats:

    * single line docstring
    * single line comment
    * function definition
    """
    try:
        first_line = cell_input.split("\n")[0]
        return first_line
    except:
        pass
    return "no description"


class RunningKernel(object):
    """
    Running a Kernel in IPython, info can be found at:
    http://ipython.org/ipython-doc/stable/development/messaging.html
    """

    def __init__(self):
        # Start an ipython kernel
        self.km = KernelManager()
        self.km.start_kernel(extra_arguments=['--matplotlib=inline'],
                             stderr=open(os.devnull, 'w'))
        # We need iopub to read every line in the cells
        """
        http://ipython.org/ipython-doc/stable/development/messaging.html

        IOPub: this socket is the 'broadcast channel' where the kernel
        publishes all side effects (stdout, stderr, etc.) as well as the
        requests coming from any client over the shell socket and its
        own requests on the stdin socket. There are a number of actions
        in Python which generate side effects: print() writes to sys.stdout,
        errors generate tracebacks, etc. Additionally, in a multi-client
        scenario, we want all frontends to be able to know what each other
        has sent to the kernel (this can be useful in collaborative scenarios,
        for example). This socket allows both side effects and the information
        about communications taking place with one client over the shell
        channel to be made available to all clients in a uniform manner.

        Check: stderr and stdout in the IPyNbException function at the end
        (if we get an error, check the msg_type and make the test to fail)
        """
        try:
            # This procedure seems to work with the newest iPython versions
            self.kc = self.km.client()
            self.kc.start_channels()
            self.iopub = self.kc.iopub_channel
        except:
            # Otherwise load it as
            self.kc = self.km
            self.kc.start_channels()
            self.iopub = self.kc.sub_channel

        # Start the shell to execute cels in the notebook (send messages?)
        self.shell = self.kc.shell_channel

    # These options are in case we wanted to restart the nb every time
    # it is executed a certain task
    def restart(self):
        self.km.restart_kernel(now=True)

    def stop(self):
        self.kc.stop_channels()
        self.km.shutdown_kernel()
        del self.km


class IPyNbFile(pytest.File):
    # Read through the specified notebooks and load the data
    # (which is in json format)
    def collect(self):
        with self.fspath.open() as f:
            self.nb = reads(f.read(), 'json')

            # Start the cell count
            cell_num = 0

            # Currently there is only 1 worksheet (it seems in newer versions
            # of iPython, they are going to get rid of this option)
            # For every worksheet, read every cell associated to it
            for ws in self.nb.worksheets:
                for cell in ws.cells:
                    # Skip the cells that have text, headings or related stuff
                    if cell.cell_type == 'code':
                            yield IPyNbCell(self.name, self, cell_num, cell)

                    # Otherwise the cell is an output cell, run it!
                    # try:
                        # This is from the prsenb code:
                        # we must change it according to this script, where
                        # the cell inspection is made by IPyNbCell
                        # outs = run_cell(shell, iopub, cell, t, tshell)
                        # yield?
                    # except Exception as e:
                    #     print "failed to run cell:", repr(e)
                    #     print cell.input

                    # Update 'code' cell count
                    cell_num += 1

    # Start the kernel with this function
    def setup(self):
        self.fixture_cell = None
        self.kernel = RunningKernel()

    def teardown(self):
        self.kernel.stop()


class IPyNbCell(pytest.Item):
    def __init__(self, name, parent, cell_num, cell):
        super(IPyNbCell, self).__init__(name, parent)

        # Get the numbers
        # We should get rid of the description (not giving
        # relevant information)
        self.cell_num = cell_num
        self.cell = cell
        self.cell_description = get_cell_description(self.cell.input)

        #
        self.comparisons = None

    def compare_outputs(self, test, ref, skip_compare=('png',
                                                       'traceback',
                                                       'latex',
                                                       'prompt_number')):
        """

        """
        self.comparisons = []

        for key in ref:
            if key not in test:
                print "missing key: %s != %s" % (test.keys(), ref.keys())
                return False
            elif (key not in skip_compare and self.sanitize(test[key]) !=
                  self.sanitize(ref[key])):

                self.comparisons.append(bcolors.FAIL
                                        + "mismatch %s:" % key
                                        + bcolors.ENDC)
                self.comparisons.append(test[key])
                self.comparisons.append('  !=  ')
                self.comparisons.append(ref[key])
                # self.comparisons.append('==============')
                # self.comparisons.append('The absolute test string:')
                # self.comparisons.append(self.sanitize(test[key]))
                # self.comparisons.append('failed to compare with the reference:')
                # self.comparisons.append(self.sanitize(ref[key]))

                # print bcolors.FAIL + "mismatch %s:" % key + bcolors.ENDC
                # print test[key]
                # print '  !=  '
                # print ref[key]
                # print bcolors.OKBLUE + 'DEBUGGING INFO' + bcolors.ENDC
                # print '=============='
                # print 'The absolute test string:'
                # print sanitize(test[key])
                # print 'failed to compare with the reference:'
                # print sanitize(ref[key])
                # print '---------------------------------------'
                # print "\n\n"
                return False
        return True

    def runtest(self):
        """
        Run all the cell tests in one kernel without restarting.
        It is very common for ipython notebooks to run through assuming a
        single kernel.
        """
        # self.parent.kernel.restart()

        # Get the current shell for executing code cells
        shell = self.parent.kernel.shell
        # Call iopub to get the messages from the executions
        iopub = self.parent.kernel.iopub

        """
        if self.parent.fixture_cell:
            shell.execute(self.parent.fixture_cell.input, allow_stdin=False)
        """


        # Execute the code from the current cell and get the msg_id of the
        #  shell process.
        msg_id = shell.execute(self.cell.input,
                               allow_stdin=False)

        """
        if (self.cell_description.lower().startswith("fixture")
            or self.cell_description.lower().startswith("setup")):
            self.parent.fixture_cell = self.cell
        """

        # Time for the reply of the cell execution
        timeout = 2000

        # This list stores the output information for the entire cell
        outs = []

        # Wait for the execution reply (we can see this in the msg_type)
        # This execution produces a dictionary where a status string can be
        # obtained: 'ok' OR 'error' OR 'abort'
        # We can also get how many cells have been executed
        # until here, with the 'execution_count' entry
        shell.get_msg(timeout=timeout)

        while True:
            """
            The messages from the cell contain information such
            as input code, outputs generated
            and other messages. We iterate through each message
            until we reach the end of the cell.
            """
            try:
                # Get one message at a time, per code block inside
                # the cell
                msg = iopub.get_msg(timeout=1.)

                # print msg['content']
                # print msg['msg_type']

                # Breaks on the last message
                # This is useful when no piece of code is left to be executed
                # in acell. It doesnt work well for us
                # if (msg.get("parent_header", None) and
                #         msg["parent_header"].get("msg_id", None) == msg_id):
                #     break
            except Empty:
                # This is not working: ! The code will not be checked
                # if the time is out (when the cell stops to be executed?)
                # raise IPyNbException("Timeout of %d seconds exceeded"
                #                      " executing cell: %s" (timeout,
                #                                             self.cell.input))
                # This is better: Just break the loop when the output is empty
                    break

            """
            Now that we have the output from a piece of code
            inside the cell,
            we want to compare the outputs of the messages
            to a reference output (the ones that are present before
            the notebook was executed)
            """

            # Firstly, get the msg type from the cell to know if
            # the output comes from a code
            # It seems that the type 'stream' is irrelevant
            msg_type = msg['msg_type']

            # REF:
            # pyin: To let all frontends know what code is being executed at
            # any given time, these messages contain a re-broadcast of the code
            # portion of an execute_request, along with the execution_count.
            if msg_type in ('status', 'pyin'):
                continue

            # If there is no more output, conitnue with the executions
            # (it will break if it is empty, with the previous statements)
            #
            # REF:
            # This message type is used to clear the output that is
            # visible on the frontend
            # elif msg_type == 'clear_output':
            #     outs = []
            #     continue

            # I added the msg_type 'idle' condition (when the cell stops)
            # so we get a complete cell output
            # REF:
            # When the kernel starts to execute code, it will enter the 'busy'
            # state and when it finishes, it will enter the 'idle' state.
            # The kernel will publish state 'starting' exactly
            # once at process startup.
            elif (msg_type == 'clear_output'
                  and msg_type['execution_state'] == 'idle'):
                outs = []
                continue

            # WE COULD ADD HERE a condition for the 'pyerr' message type
            # Making the test to fail

            """
            Now we get the reply from the piece of code executed
            and analyse the outputs
            """
            reply = msg['content']
            out = NotebookNode(output_type=msg_type)

            # Now check what type of output it is
            if msg_type == 'stream':
                out.stream = reply['name']
                out.text = reply['data']
            elif msg_type in ('display_data', 'pyout'):
                # REF:
                # data and metadata are identical to a display_data message.
                # the object being displayed is that passed to the display
                #  hook, i.e. the *result* of the execution.
                out['metadata'] = reply['metadata']
                for mime, data in reply['data'].iteritems():
                    attr = mime.split('/')[-1].lower()
                    attr = attr.replace('+xml', '').replace('plain', 'text')
                    setattr(out, attr, data)
                if msg_type == 'pyout':
                    out.prompt_number = reply['execution_count']
            else:
                print "unhandled iopub msg:", msg_type

            # print 'OUT STATUS ========='
            # print outs
            outs.append(out)

        """
        This message is the last message of the cell, which contains no output.
        It only indicates whether the entire cell ran successfully or if there
        was an error.
        """
        reply = msg['content']

        # DEBUG::::::::::::::::::::::::::::::::::::::::::::::::::
        # We need to get the reference from the outputs that are already
        # in the notebook
        # print '============= REFERENCE ??? ======== \n'
        # print self.cell.outputs
        # print '\n\n'

        # We need to get the reference from the outputs that are already
        # in the notebook
        # print '============= OUTPUT ??? ======== \n'
        # print outs
        # print '\n\n'
        # ::::::::::::::::::::::::::::::::::::::::::::::::::::::::

        failed = False
        for out, ref in zip(outs, self.cell.outputs):
            if not self.compare_outputs(out, ref):
                failed = True

        # if failed:
        #     failures += 1
        # else:
        #     successes += 1
        # sys.stdout.write('.')

        # raise NotImplementedError

        # if reply['status'] == 'error':
        # Traceback is only when an error is raised (?)

        # We usually get an exception because traceback is not defined
        if failed:  # Use this to make the test fail
            # raise IPyNbException(self.cell_num,
            #                      self.cell_description,
            #                      self.cell.input,
            #                      '\n'.join(reply['traceback']))
            """
            The pytest exception will be raised if there are any
            errors in the notebook cells. Now we check that
            the outputs produced from running each cell
            matches the outputs in the existing notebook.
            This code is taken from [REF].
            """
            raise IPyNbException(self.cell_num,
                                 self.cell_description,
                                 self.cell.input,
                                 # Here we must put the traceback output:
                                 '\n'.join(self.comparisons))

    def sanitize(self, s):
        """sanitize a string for comparison.

        fix universal newlines, strip trailing newlines,
        and normalize likely random values (memory addresses and UUIDs)
        """
        if not isinstance(s, basestring):
            return s

        """
        re.sub matches a regex and replaces it with another. It
        is used to find finmag stamps (Time and date followed by INFO,
        DEBUG, WARNING) and the whole line is replaced with a single
        word.
        """
        s = re.sub(r'\[.*\] INFO:.*', 'FINMAG INFO:', s)
        s = re.sub(r'\[.*\] DEBUG:.*', 'FINMAG DEBUG:', s)
        s = re.sub(r'\[.*\] WARNING:.*', 'FINMAG WARNING:', s)

        """
        Using the same method we strip UserWarnings from matplotlib
        """
        s = re.sub(r'.*/matplotlib/.*UserWarning:.*',
                   'MATPLOTLIB USERWARNING', s)

        # Also for gmsh information lines
        s = re.sub(r'Info    :.*', 'GMSH INFO', s)

        # normalize newline:
        s = s.replace('\r\n', '\n')

        # ignore trailing newlines (but not space)
        s = s.rstrip('\n')

        # normalize hex addresses:
        s = re.sub(r'0x[a-f0-9]+', '0xFFFFFFFF', s)

        # normalize UUIDs:
        s = re.sub(r'[a-f0-9]{8}(\-[a-f0-9]{4}){3}\-[a-f0-9]{12}',
                   'U-U-I-D', s)

        return s

    def repr_failure(self, excinfo):
        """ called when self.runtest() raises an exception. """
        if isinstance(excinfo.value, IPyNbException):
            return "\n".join([
                "Notebook execution failed",
                "Cell %d: %s\n\n"
                "Input:\n%s\n\n"
                "Traceback:\n%s\n" % excinfo.value.args,
            ])
        else:
            return "pytest plugin exception: %s" % str(excinfo.value)

    def reportinfo(self):
        description = "cell %d" % self.cell_num
        if self.cell_description:
            description += ": " + self.cell_description
        return self.fspath, 0, description
