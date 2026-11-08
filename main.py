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
SIDEBAR_WIDTH = 140            # width of the button bar on the far left
PANEL_WIDTH = 260              # width of the settings panel that opens next to it

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
        self.resize(*WINDOW_SIZE)
        self.setStyleSheet(STYLESHEET)

        self.create_UI()                                         # build the screen
        self.startButton.clicked.connect(self.open_main_window)  # wire the button

    def create_UI(self):
        self.startButton = QPushButton("Start")
        self.titleText = QLabel("Catastrophic Forgetting")
        self.titleText.setStyleSheet("font-size: 30px;")
        self.titleText.setAlignment(Qt.AlignCenter)   # center the text inside the label

        layout = QVBoxLayout()
        layout.addStretch()                            # equal stretches above and below keep it centered
        layout.addWidget(self.titleText)
        layout.addWidget(self.startButton, alignment=Qt.AlignHCenter)
        layout.addStretch()

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    def open_main_window(self):
        self.main_window = MainWindow()
        self.main_window.show()
        self.close()


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
        graph_layout = self.build_left_side()
        sidebar = self.build_sidebar()
        settings_panel = self.build_settings_panel()
        self.assemble_window(sidebar, settings_panel, graph_layout)

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

    def build_sidebar(self):
        """Far-left bar: the Settings toggle at the top, the action buttons at the bottom."""
        self.settingsButton = QPushButton("Settings")
        self.settingsButton.setCheckable(True)      # stays pressed while the panel is open

        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)
        layout.addWidget(self.settingsButton)
        layout.addStretch()                         # empty space that pushes the buttons down
        layout.addWidget(self.applyButton)
        layout.addWidget(self.runButton)
        return sidebar

    def build_settings_panel(self):
        """A scrollable column of settings. It sits next to the sidebar and starts hidden."""
        container = QWidget()
        layout = QVBoxLayout(container)

        # Order here = order on screen. Move a line to move a control.
        add_setting(layout, "Learning Rate", self.learningRateBox)
        add_setting(layout, "Random Seed", self.seedBox)
        add_setting(layout, "Epochs Per Run", self.epochsBox)
        add_setting(layout, "Learning Method", self.methodBox)
        add_setting(layout, "Model", self.modelBox)
        layout.addStretch()                         # keeps the controls packed at the top

        scroll_area = QScrollArea()
        scroll_area.setWidget(container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedWidth(PANEL_WIDTH)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.hide()                          # closed until Settings is pressed
        return scroll_area

    def assemble_window(self, sidebar, settings_panel, graph_layout):
        """Left to right: sidebar, settings panel (when open), graph."""
        central = QWidget()
        row = QHBoxLayout(central)
        row.addWidget(sidebar)
        row.addWidget(settings_panel)
        row.addLayout(graph_layout, 1)              # the graph takes all leftover width
        self.setCentralWidget(central)

        self.settingsButton.toggled.connect(settings_panel.setVisible)  # pressed = open

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
