import math
import random
import sys
import time

from PySide6.QtCore import QPointF, Qt, QThread, QTimer, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget, QGraphicsScene, QGraphicsView, QSlider)
import AI
import nodeSystem

WINDOW_SIZE = (1000, 600)
SIDEBAR_WIDTH = 120
PANEL_WIDTH = 260

STYLESHEET = """
"""

MAIN_STYLESHEET = """
QMainWindow, QWidget#page { background-color: #000000; }
QWidget { color: #e6e6e6; }
QLabel { background: transparent; }

QWidget#sidebar, QWidget#settingsContent, QScrollArea#settingsPanel,
QScrollArea#settingsPanel QWidget#qt_scrollarea_viewport { background-color: #141414; }
QScrollArea#settingsPanel { border: none; }

QWidget#graphArea { background-color: #000000; border: 1px solid #1c1c1c; }
QPlainTextEdit { background-color: #000000; color: #e6e6e6; border: none; }

QPushButton { background-color: #262626; border: 1px solid #3a3a3a; border-radius: 4px; padding: 6px; }
QPushButton:hover { background-color: #333333; }
QPushButton:pressed, QPushButton:checked { background-color: #404040; }
QPushButton:disabled { background-color: #1c1c1c; color: #777777; }

QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #262626; border: 1px solid #3a3a3a; border-radius: 4px; padding: 3px;
}
QComboBox QAbstractItemView {
    background-color: #1c1c1c; border: 1px solid #3a3a3a; selection-background-color: #404040;
}

QScrollBar:vertical { background: #141414; width: 10px; }
QScrollBar::handle:vertical { background: #3a3a3a; border-radius: 5px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QSlider::groove:horizontal { background: #3a3a3a; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #777777; border-radius: 2px; }
QSlider::handle:horizontal { background: #e6e6e6; width: 12px; margin: -5px 0; border-radius: 6px; }
QSlider::handle:horizontal:disabled { background: #555555; }
"""

NODE_COUNT = 40
NODE_SPEED = 10
LINK_DISTANCE = 140
BACKGROUND_COLOR = (0, 0, 0)
NODE_COLOR = (255, 255, 255)



# 
class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)


    def __init__(self, function, *args):
        super().__init__()
        self.function = function
        self.args = args

    # Run the job and send the result through done or the error text through failed
    # Qt calls this automatically when the worker is started
    def run(self):
        try:
            self.done.emit(self.function(*self.args))
        except Exception as error:
            self.failed.emit(str(error))


# Put a text label and a control into a layout one above the other
# Takes
#    layout the layout to add them to
#    label_text str the text shown above the control
#    widget the control itself such as a spin box or a combo box
def add_setting(layout, label_text, widget):
    layout.addWidget(QLabel(label_text))
    layout.addWidget(widget)



# Node System
class NodePage(QWidget):
     def __init__(self):
            super().__init__()

            nodes = {
                "Node_A": {"status": "Active", "load": 45},
                "Node_B": {"status": "Active", "load": 85},
                "Node_C": {"status": "Inactive", "load": 0},
                "Node_D": {"status": "Active", "load": 30}
            }

            connections = [
                ("Node_A", "Node_B"),
                ("Node_B", "Node_C"),
                ("Node_A", "Node_D")
            ]

            for nodeName, nodeData in nodes.items():
                print(nodeName)
                print(nodeData)














class DriftingNodes(QWidget):
    # Create the animated background white dots that drift and connect with fading lines
    # Put a layout on this widget to place other widgets on top of it
    def __init__(self):
        super().__init__()
        self.last_tick = time.monotonic()
        self.nodes = []
        for _ in range(NODE_COUNT):
            angle = random.uniform(0, 2 * math.pi)
            speed = NODE_SPEED * random.uniform(0.5, 1.5)
            self.nodes.append({
                "x": random.uniform(0, WINDOW_SIZE[0]), "y": random.uniform(0, WINDOW_SIZE[1]),
                "vx": math.cos(angle) * speed, "vy": math.sin(angle) * speed,
                "size": random.uniform(2.0, 3.5),
            })

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.step)

    # Start the animation when the widget appears on screen
    # Takes event the show event from qt passed in automatically
    def showEvent(self, event):
        super().showEvent(event)
        self.last_tick = time.monotonic()
        self.timer.start(16)

    # Stop the animation when the widget is hidden or closed
    # Takes event the hide event from qt passed in automatically
    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    # Move every dot a little wrapping around the window edges then redraw
    # Called by the timer about 60 times per second
    def step(self):
        now = time.monotonic()
        dt = min(now - self.last_tick, 0.05)
        self.last_tick = now
        width, height = max(self.width(), 1), max(self.height(), 1)
        for node in self.nodes:
            node["x"] = (node["x"] + node["vx"] * dt) % width
            node["y"] = (node["y"] + node["vy"] * dt) % height
        self.update()

    # Draw the black background the lines between nearby dots then the dots
    # Takes event the paint event from qt passed in automatically
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(*BACKGROUND_COLOR))

        for i, a in enumerate(self.nodes):
            for b in self.nodes[i + 1:]:
                distance = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                if distance >= LINK_DISTANCE:
                    continue
                closeness = 1 - distance / LINK_DISTANCE
                painter.setPen(QPen(QColor(*NODE_COLOR, int(140 * closeness)), 1.0))
                painter.drawLine(QPointF(a["x"], a["y"]), QPointF(b["x"], b["y"]))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*NODE_COLOR, 230))
        for node in self.nodes:
            painter.drawEllipse(QPointF(node["x"], node["y"]), node["size"], node["size"])


class StartWindow(QMainWindow):
    # Create the start screen and connect its start button
    def __init__(self):
        super().__init__()
        self.resize(*WINDOW_SIZE)
        self.setStyleSheet(STYLESHEET)

        self.create_UI()
        self.startButton.clicked.connect(self.open_main_window)

    # Build the start screen with a centered title and the start button below it
    def create_UI(self):
        self.startButton = QPushButton("Start")
        self.titleText = QLabel("Catastrophic Forgetting")
        self.titleText.setStyleSheet("font-size: 30px; color: white;")
        self.titleText.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(self.titleText)
        layout.addWidget(self.startButton, alignment=Qt.AlignHCenter)
        layout.addStretch()

        central = DriftingNodes()
        central.setLayout(layout)
        self.setCentralWidget(central)

    # Switch the start screen for main screen without in the same window
    # Called when the start button is clicked
    def open_main_window(self):
        self.main_window = MainWindow()
        self.setCentralWidget(self.main_window)


class MainWindow(QMainWindow):
    progress = Signal(str)

    # Create the main window build its layout and start loading the model
    def __init__(self):
        super().__init__()
        self.resize(*WINDOW_SIZE)
        self.setStyleSheet(MAIN_STYLESHEET)

        self.experiment = None
        self.worker = None
        self.graphBuilt = False
        self.create_controls()
        graph_layout = self.build_left_side()
        sidebar = self.build_sidebar()
        settings_panel = self.build_settings_panel()
        self.assemble_window(sidebar, settings_panel, graph_layout)

        self.applyButton.clicked.connect(self.apply_changes)
        self.runButton.clicked.connect(self.run_session)
        self.historySlider.valueChanged.connect(self.show_history)
        self.progress.connect(self.show_message)

        self.apply_changes()

    # Create every setting control and the apply changes and run session buttons
    # Placement on screen happens in the build_ methods
    def create_controls(self):
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

        self.applyButton = QPushButton("Apply Changes")
        self.runButton = QPushButton("Run Session")

        self.historyLabel = QLabel("History 0/0")
        self.historySlider = QSlider(Qt.Horizontal)
        self.historySlider.setRange(0, 0)




    # Build the graph area a title label above the text log
    # Returns the layout holding them
    def build_left_side(self):
        layout = QVBoxLayout()

        self.titleLabel = QLabel(" Node Graph ")
        layout.addWidget(self.titleLabel)

        self.scene = QGraphicsScene()
        self.scene.setBackgroundBrush(QColor(0, 0, 0))
        self.graphArea = QGraphicsView(self.scene)
        self.graphArea.setRenderHint(QPainter.Antialiasing)
        self.graphArea.setObjectName("graphArea")
        layout.addWidget(self.graphArea, 3)



        self.terminalLabel = QLabel(" Terminal ")
        layout.addWidget(self.terminalLabel)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

        return layout




    # Build the sidebar with settings and style buttons on top and apply and run at the bottom
    # Returns the sidebar widget
    def build_sidebar(self):
        self.settingsButton = QPushButton("Settings")

        self.settingsButton.setCheckable(True)

        self.settingsButton.setCheckable(True)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)

        layout.addWidget(self.settingsButton)


        layout.addStretch()
        layout.addWidget(self.historyLabel)
        layout.addWidget(self.historySlider)
        layout.addWidget(self.applyButton)
        layout.addWidget(self.runButton)
        return sidebar

    # Build the scrollable settings panel that opens next to the sidebar and starts hidden
    # Returns the panel widget
    def build_settings_panel(self):
        container = QWidget()
        container.setObjectName("settingsContent")
        container.setFixedWidth(PANEL_WIDTH)
        layout = QVBoxLayout(container)

        add_setting(layout, "Learning Rate", self.learningRateBox)
        add_setting(layout, "Random Seed", self.seedBox)
        add_setting(layout, "Epochs Per Run", self.epochsBox)
        add_setting(layout, "Learning Method", self.methodBox)
        add_setting(layout, "Model", self.modelBox)
        layout.addStretch()

        scroll_area = QScrollArea()
        scroll_area.setObjectName("settingsPanel")
        scroll_area.setWidget(container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumWidth(0)
        scroll_area.setMaximumWidth(0)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return scroll_area

    # Place the sidebar settings panel and graph side by side and wire the settings button
    def assemble_window(self, sidebar, settings_panel, graph_layout):
        central = QWidget()
        central.setObjectName("page")
        row = QHBoxLayout(central)
        row.addWidget(sidebar)
        row.addWidget(settings_panel)
        row.addLayout(graph_layout, 1)
        self.setCentralWidget(central)

        self.panelAnimation = QPropertyAnimation(settings_panel, b"maximumWidth")
        self.panelAnimation.setDuration(300)
        self.panelAnimation.setEasingCurve(QEasingCurve.InOutCubic)
        self.panelAnimation.valueChanged.connect(settings_panel.setMinimumWidth)
        self.settingsButton.toggled.connect(self.slide_settings_panel)

    # Slide animation for the settings panel
    # Uses a bool value to decide whether to slide the panel out or back in
    def slide_settings_panel(self, opening):
        self.panelAnimation.stop()
        self.panelAnimation.setStartValue(self.panelAnimation.targetObject().maximumWidth())
        self.panelAnimation.setEndValue(PANEL_WIDTH if opening else 0)
        self.panelAnimation.start()

    # Add one line of text to the log
    # Takes text str the line to add
    def show_message(self, text):
        self.log.appendPlainText(text)

    # Write the results of a finished lesson to the log
    # Takes result dict the lesson summary returned by teach_next_lesson
    def show_lesson_result(self, result):
        self.show_message(f"--- Lesson {result['lesson']}/{AI.N_LESSONS} done "
                          f"(final loss {result['loss']:.3f}) ---")
        self.show_message(f"New facts:  {result['new_before']:.0%} -> {result['new_after']:.0%} confidence")

        if result["old_before"] is not None:
            self.show_message(f"Old facts:  {result['old_before']:.0%} -> {result['old_after']:.0%} "
                              f"confidence (a drop here is forgetting)")

        weakest = sorted(result["facts"], key=lambda fact: fact["confidence"])[:3]
        self.show_message("Weakest facts: " + ", ".join(
            f"{fact['subject']} ({fact['confidence']:.0%})" for fact in weakest))
        self.show_message(f"Saved to {AI.RESULTS_FILE}")

        if not self.graphBuilt:
            nodeSystem.loadGraph(self.experiment.facts, self.experiment.links)
            nodeSystem.drawNodes(self.scene)
            for a, b in nodeSystem.connections:
                nodeSystem.connectNodes(self.scene, a, b)
            nodeSystem.saveHistory()
            area = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
            self.scene.setSceneRect(area)
            self.graphArea.fitInView(area, Qt.KeepAspectRatio)
            self.graphBuilt = True

        newConfidence = {fact["fact_id"]: fact["confidence"] * 100 for fact in result["facts"]}
        newStrengths = {(row["from_fact"], row["to_fact"]): row["dependency"] * 100 for row in result["links"]}
        nodeSystem.updateNodes(newConfidence)
        nodeSystem.updateConnections(newStrengths)
        nodeSystem.saveHistory()

        self.historySlider.setMaximum(len(nodeSystem.history) - 1)
        self.historySlider.setValue(self.historySlider.maximum())

    # Shows the graph as it was at a point in history and updates the label under the slider
    # Takes value the slider position which is the index of the snapshot in history
    def show_history(self, value):
        nodeSystem.readHistory(value)
        self.historyLabel.setText(f"History {value}/{self.historySlider.maximum()}")

    # Start a brand new experiment using the chosen model method and seed
    # Called by the apply changes button and once when the window opens
    def apply_changes(self):
        model = self.modelBox.currentText()
        method = self.methodBox.currentText()
        self.experiment = None
        self.log.clear()
        self.scene.clear()
        nodeSystem.clearGraph()
        self.graphBuilt = False
        self.historySlider.setMaximum(0)
        self.historySlider.setValue(0)
        self.historyLabel.setText("History 0/0")
        self.show_message(f"Loading {model} ({method}). The first time, the model downloads, "
                          f"so this can take a while...")
        self.start_task(AI.Experiment, self.on_experiment_loaded, model, method, self.seedBox.value())

    # Store the loaded experiment and tell the user it is ready
    # Takes experiment the experiment that finished loading
    def on_experiment_loaded(self, experiment):
        self.experiment = experiment
        experiment.progress = self.progress.emit
        self.show_message(f"Ready on {experiment.device.upper()}: {experiment.model_name}, "
                          f"{experiment.method}, seed {experiment.seed}.")
        self.show_message(AI.METHOD_TIPS[experiment.method])
        self.show_message("Press Run Session to teach lesson 1.")

    # Teach the next lesson using the current learning rate and epochs
    # Called by the run session button
    def run_session(self):
        if self.experiment is None:
            self.show_message("The model isn't loaded yet.")
            return
        self.show_message(f"Teaching lesson {self.experiment.lesson + 1}...")
        self.start_task(self.experiment.teach_next_lesson, self.show_lesson_result,
                        self.learningRateBox.value(), self.epochsBox.value())

    # Run a slow function in the background so the window stays responsive
    # Takes
    #    function the function to run in the background
    #    on_done a function called with the result when the job finishes
    #    *args the arguments to pass to function
    def start_task(self, function, on_done, *args):
        self.set_busy(True)
        self.worker = Worker(function, *args)
        self.worker.done.connect(lambda result: self.finish_task(on_done, result))
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    # Re enable the buttons then pass the result of the finished job to its handler
    # Takes
    #    on_done the function to call with the result
    #    result what the background job returned
    def finish_task(self, on_done, result):
        self.set_busy(False)
        on_done(result)

    # Re enable the buttons and show the error in the log
    # Takes error str the error message from the failed job
    def on_failed(self, error):
        self.set_busy(False)
        self.show_message(f"ERROR: {error}")

    # Turn the run session and apply changes buttons off or on
    # Takes busy bool true disables the buttons while the ai is working and false enables them
    def set_busy(self, busy):
        self.runButton.setEnabled(not busy)
        self.applyButton.setEnabled(not busy)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StartWindow()
    window.show()
    sys.exit(app.exec())