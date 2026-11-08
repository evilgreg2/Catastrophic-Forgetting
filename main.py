import sys

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

import AI

# ============================================================================
# SETTINGS: change these first when restyling
# ============================================================================
WINDOW_SIZE = (1000, 600)      # width, height in pixels
PANEL_WIDTH = 260              # width of the settings column on the right

STYLESHEET = """
"""


# ============================================================================
# Worker: runs a slow function in the background
# ============================================================================
class Worker(QThread):
    done = Signal(object)      # sent when the job finishes, carrying its result
    failed = Signal(str)       # sent if the job crashes, carrying the error text

    def __init__(self, function, *args):
        super().__init__()
        self.function = function
        self.args = args

    def run(self):
        try:
            self.done.emit(self.function(*self.args))
        except Exception as error:
            self.failed.emit(str(error))


def add_setting(layout, label_text, widget):
    """Put a label and its control into a layout, one above the other."""
    layout.addWidget(QLabel(label_text))
    layout.addWidget(widget)



class StartWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize(*WINDOW_SIZE) # Why the * next to WINDOW_SIZE??
        self.setStyleSheet(STYLESHEET)

        self.create_UI()                                         # build the screen
        self.startButton.clicked.connect(self.open_main_window)  # wire the button

    def create_UI(self):
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Catastrophic Forgetting"))
        self.startButton = QPushButton("Start")
        layout.addWidget(self.startButton)

        central = QWidget()                 # a container to hold the layout
        central.setLayout(layout)
        self.setCentralWidget(central)



    def open_main_window(self):
        self.main_window = MainWindow()     # save it on self so Python doesn't delete it
        self.main_window.show()
        self.close()                        # close the intro screen



        
# ============================================================================
# The main window
# ============================================================================
class MainWindow(QMainWindow):
    progress = Signal(str)     # AI.py sends live messages through this into the log

    def __init__(self):
        super().__init__()
        self.resize(*WINDOW_SIZE)
        self.setStyleSheet(STYLESHEET)

        self.experiment = None     # the current AI.Experiment (None while loading)
        self.worker = None         # the background job currently running

        self.create_controls()
        left_side = self.build_left_side()
        right_side = self.build_right_panel()
        self.assemble_window(left_side, right_side)

        # Connect buttons and signals to the methods that handle them
        self.applyButton.clicked.connect(self.apply_changes)
        self.runButton.clicked.connect(self.run_session)
        self.progress.connect(self.show_message)

        self.apply_changes()       # load the model as soon as the app opens




    # ========================================================================
    # A. BUILD THE UI
    # ========================================================================
    def create_controls(self):
        """Create every setting widget in one place. Layout happens later."""
        self.learningRateBox = QDoubleSpinBox()
        self.learningRateBox.setDecimals(5)
        self.learningRateBox.setRange(0.00001, 0.01)
        self.learningRateBox.setSingleStep(0.0001)
        self.learningRateBox.setValue(0.0002)

        self.seedBox = QSpinBox()
        self.seedBox.setRange(0, 9999)
        self.seedBox.setValue(42)

        self.epochsBox = QSpinBox()
        self.epochsBox.setRange(1, 1000)
        self.epochsBox.setValue(10)

        self.methodBox = QComboBox()
        self.methodBox.addItems(AI.METHODS)

        self.modelBox = QComboBox()
        self.modelBox.addItems(list(AI.MODELS))

        self.applyButton = QPushButton("Apply Changes")   # starts a NEW experiment
        self.runButton = QPushButton("Run Session")       # teaches the next lesson

    def build_left_side(self):
        """Left side: a title, then the main display area."""
        layout = QVBoxLayout()

        self.titleLabel = QLabel(" Node Graph ")
        layout.addWidget(self.titleLabel)

        # TEMPORARY: a text log. Replace this line with the node graph widget later.
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)       # the 1 lets it take all leftover space

        return layout

    def build_right_panel(self):
        """Right side: a scrollable column of settings, with the buttons at the bottom."""
        container = QWidget()
        layout = QVBoxLayout(container)

        # Order here = order on screen. Move a line to move a control.
        add_setting(layout, "Learning Rate", self.learningRateBox)
        add_setting(layout, "Random Seed", self.seedBox)
        add_setting(layout, "Epochs Per Run", self.epochsBox)
        add_setting(layout, "Learning Method", self.methodBox)
        add_setting(layout, "Model", self.modelBox)

        layout.addStretch()                 # empty space that pushes the buttons down
        layout.addWidget(self.applyButton)
        layout.addWidget(self.runButton)

        scroll_area = QScrollArea()
        scroll_area.setWidget(container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(PANEL_WIDTH)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll_area

    def assemble_window(self, left_side, right_side):
        """Put the left side and the right panel next to each other."""
        central = QWidget()
        row = QHBoxLayout(central)
        row.addLayout(left_side, 1)         # left side takes all leftover width
        row.addWidget(right_side)           # right panel keeps its fixed width
        self.setCentralWidget(central)





    # ========================================================================
    # B. SHOW RESULTS
    # ========================================================================
    def show_message(self, text):
        """Add one line to the log."""
        self.log.appendPlainText(text)

    def show_lesson_result(self, result):
        """Called after each lesson finishes. `result` is the dict from AI.py."""
        self.show_message(f"--- Lesson {result['lesson']}/{AI.N_LESSONS} done "
                          f"(final loss {result['loss']:.3f}) ---")
        self.show_message(f"New facts:  {result['new_before']:.0%} -> {result['new_after']:.0%} confidence")

        if result["old_before"] is not None:     # lesson 1 has no old facts yet
            self.show_message(f"Old facts:  {result['old_before']:.0%} -> {result['old_after']:.0%} "
                              f"confidence (a drop here is forgetting)")

        weakest = sorted(result["facts"], key=lambda fact: fact["confidence"])[:3]
        self.show_message("Weakest facts: " + ", ".join(
            f"{fact['subject']} ({fact['confidence']:.0%})" for fact in weakest))
        self.show_message(f"Saved to {AI.RESULTS_FILE}")

        # FUTURE: update the node graph here, for example:
        #   self.graph.update_nodes(result["facts"])

    # ========================================================================
    # C. BUTTON ACTIONS
    # ========================================================================
    def apply_changes(self):
        """'Apply Changes' button: start a brand-new experiment with the chosen model/method/seed."""
        model = self.modelBox.currentText()
        method = self.methodBox.currentText()
        self.experiment = None
        self.log.clear()
        self.show_message(f"Loading {model} ({method}). The first time, the model downloads, "
                          f"so this can take a while...")
        self.start_task(AI.Experiment, self.on_experiment_loaded, model, method, self.seedBox.value())

    def on_experiment_loaded(self, experiment):
        """Runs when the model has finished loading."""
        self.experiment = experiment
        experiment.progress = self.progress.emit    # live training messages go to the log
        self.show_message(f"Ready on {experiment.device.upper()}: {experiment.model_name}, "
                          f"{experiment.method}, seed {experiment.seed}.")
        self.show_message(AI.METHOD_TIPS[experiment.method])
        self.show_message("Press Run Session to teach lesson 1.")

    def run_session(self):
        """'Run Session' button: teach the next lesson using the current learning rate and epochs."""
        if self.experiment is None:
            self.show_message("The model isn't loaded yet.")
            return
        self.show_message(f"Teaching lesson {self.experiment.lesson + 1}...")
        self.start_task(self.experiment.teach_next_lesson, self.show_lesson_result,
                        self.learningRateBox.value(), self.epochsBox.value())

    # ========================================================================
    # D. BACKGROUND PLUMBING (no need to edit when redesigning the UI)
    # ========================================================================
    def start_task(self, function, on_done, *args):
        """Run function(*args) in the background, then call on_done(result) when it finishes."""
        self.set_busy(True)
        self.worker = Worker(function, *args)
        self.worker.done.connect(lambda result: self.finish_task(on_done, result))
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def finish_task(self, on_done, result):
        self.set_busy(False)
        on_done(result)

    def on_failed(self, error):
        self.set_busy(False)
        self.show_message(f"ERROR: {error}")

    def set_busy(self, busy):
        """Disable the buttons while the AI is working so you can't start two jobs at once."""
        self.runButton.setEnabled(not busy)
        self.applyButton.setEnabled(not busy)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StartWindow()
    window.show()
    sys.exit(app.exec())