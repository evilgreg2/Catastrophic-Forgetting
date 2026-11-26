import hashlib
import math
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import Property, QPointF, Qt, QThread, QTimer, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel,
                               QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget, QSlider)
import graph
import nodeSystem

AI = None


# AI imports torch which is slow, so it only loads once the window is already up
def loadAI():
    global AI
    import AI as ai
    AI = ai


fontPath = Path(__file__).resolve().parent / "fonts" / "Exo2-Light.ttf"
fontUrl = "https://raw.githubusercontent.com/googlefonts/Exo-2.0/master/fonts/ttf/Exo2-Light.ttf"
fontHash = "5bc24704e513d033e71780825684611b907008db7609d6c265cef212200c2a82"
fontReady = False


# grabs the font on first run and checks the hash so we know it's the real file
def downloadFont():
    if fontPath.exists():
        return
    data = urllib.request.urlopen(fontUrl, timeout=15).read()
    if hashlib.sha256(data).hexdigest() != fontHash:
        raise RuntimeError("file didn't match its checksum")
    fontPath.parent.mkdir(exist_ok=True)
    fontPath.write_bytes(data)


# everything slow the start screen waits on, a font failure isn't fatal so it just gets returned as a note
def loadAll():
    note = None
    try:
        downloadFont()
    except Exception as err:
        note = f"Couldn't download the font ({err}), using the default one"
    loadAI()
    return note


# sets the app font once the file exists
def useFont():
    global fontReady
    if fontReady or not fontPath.exists():
        return
    fid = QFontDatabase.addApplicationFont(str(fontPath))
    if fid < 0:
        return
    QApplication.setFont(QFont(QFontDatabase.applicationFontFamilies(fid)[0], 9))
    fontReady = True


WINDOW_SIZE = (1500, 900)
SIDEBAR_WIDTH = 200
PANEL_WIDTH = 260

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

NODE_COUNT = 70
NODE_SPEED = 10
LINK_DISTANCE = 140
BACKGROUND_COLOR = (0, 0, 0)
NODE_COLOR = (255, 255, 255)
GLOW_RADIUS_SCALE = 9
GLOW_ALPHA = 90


class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)


    # stores what to run and the args for it
    def __init__(self, function, *args):
        super().__init__()
        self.function = function
        self.args = args

    # runs the function off the main thread and sends back the result or the error
    def run(self):
        try:
            self.done.emit(self.function(*self.args))
        except Exception as error:
            self.failed.emit(str(error))


# label on top, control under it
def add_setting(layout, label_text, widget):
    layout.addWidget(QLabel(label_text))
    layout.addWidget(widget)


class DriftingNodes(QWidget):
    # makes the dots with random spots and speeds, plus the haze and timer
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

        self.hazeData = graph.hazePixels(1024)
        self.haze = QImage(self.hazeData.data, 1024, 1024, 1024, QImage.Format_Grayscale8)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.step)

    # start moving the dots when the widget shows up
    def showEvent(self, event):
        super().showEvent(event)
        self.last_tick = time.monotonic()
        self.timer.start(16)

    # stop the timer when it's hidden so it isn't running for nothing
    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    # moves every dot a bit and wraps them around the edges
    def step(self):
        now = time.monotonic()
        dt = min(now - self.last_tick, 0.05)
        self.last_tick = now
        width, height = max(self.width(), 1), max(self.height(), 1)
        for node in self.nodes:
            node["x"] = (node["x"] + node["vx"] * dt) % width
            node["y"] = (node["y"] + node["vy"] * dt) % height
        self.update()

    # background, haze, lines between close dots, then glow and the dots
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(*BACKGROUND_COLOR))
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawImage(self.rect(), self.haze)

        for i, a in enumerate(self.nodes):
            for b in self.nodes[i + 1:]:
                distance = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                if distance >= LINK_DISTANCE:
                    continue
                closeness = 1 - distance / LINK_DISTANCE
                painter.setPen(QPen(QColor(*NODE_COLOR, int(140 * closeness)), 1.0))
                painter.drawLine(QPointF(a["x"], a["y"]), QPointF(b["x"], b["y"]))

        painter.setPen(Qt.NoPen)

        # plus mode so overlapping glows add up
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        for node in self.nodes:
            pos = QPointF(node["x"], node["y"])
            r = node["size"] * GLOW_RADIUS_SCALE
            glow = QRadialGradient(pos, r)
            glow.setColorAt(0, QColor(*NODE_COLOR, GLOW_ALPHA))
            glow.setColorAt(0.35, QColor(*NODE_COLOR, 20))
            glow.setColorAt(1, QColor(*NODE_COLOR, 0))
            painter.setBrush(glow)
            painter.drawEllipse(pos, r, r)

        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setBrush(QColor(*NODE_COLOR, 230))
        for node in self.nodes:
            painter.drawEllipse(QPointF(node["x"], node["y"]), node["size"], node["size"])


class StartButton(QPushButton):
    # text size starts at 20 and has an animation for the hover grow
    def __init__(self, text):
        super().__init__(text)
        self.normalSize = 20
        self.grow = QPropertyAnimation(self, b"textSize")
        self.grow.setDuration(120)
        self.setTextSize(self.normalSize)

    # getter for the textSize property below
    def getTextSize(self):
        return self.font().pixelSize()

    # setter for the textSize property so it can be animated
    def setTextSize(self, size):
        font = self.font()
        font.setPixelSize(size)
        self.setFont(font)

    textSize = Property(int, getTextSize, setTextSize)

    # text grows a little when the mouse is over the button
    def enterEvent(self, event):
        self.grow.stop()
        self.grow.setEndValue(self.normalSize + 2)
        self.grow.start()
        super().enterEvent(event)

    # text shrinks back when the mouse leaves
    def leaveEvent(self, event):
        self.grow.stop()
        self.grow.setEndValue(self.normalSize)
        self.grow.start()
        super().leaveEvent(event)


class StartWindow(QMainWindow):
    # loads the AI in the background and keeps the start button locked until it's done
    def __init__(self):
        super().__init__()
        self.resize(*WINDOW_SIZE)

        self.create_UI()
        self.startButton.clicked.connect(self.open_main_window)

        self.startButton.setEnabled(False)
        self.startButton.setText("Loading...")
        self.loader = Worker(loadAll)
        self.loader.done.connect(self.aiReady)
        self.loader.failed.connect(self.aiFailed)
        QTimer.singleShot(50, self.loader.start)

    # loading finished, so unlock the start button
    def aiReady(self, result):
        if result:
            print(result)
        useFont()
        self.titleText.setStyleSheet(self.titleText.styleSheet())
        self.subtitleText.setStyleSheet(self.subtitleText.styleSheet())
        self.startButton.setText("Start")
        self.startButton.setEnabled(True)

    # the AI didn't load so there's nothing to start
    def aiFailed(self, error):
        self.startButton.setText("Couldn't load AI")

    # title, subtitle and start button on top of the moving dots
    def create_UI(self):
        self.startButton = StartButton("Start")
        self.startButton.setMinimumSize(210, 50)
        self.startButton.setStyleSheet("""
            QPushButton { background-color: #262626; color: #e6e6e6; border: 1px solid #3a3a3a; border-radius: 4px; }
            QPushButton:hover { background-color: #333333; }
            QPushButton:pressed { background-color: #404040; }
            QPushButton:disabled { background-color: #1c1c1c; color: #777777; }
        """)
        self.titleText = QLabel("Recall")
        self.titleText.setStyleSheet("font-size: 48px; font-weight: 300; letter-spacing: 4px; color: white;")
        self.titleText.setAlignment(Qt.AlignCenter)
        self.subtitleText = QLabel("Local AI Model Learning and Forgetting Visualizer")
        self.subtitleText.setStyleSheet("font-size: 16px; letter-spacing: 2px; color: #aaaaaa;")
        self.subtitleText.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        layout.addStretch()
        layout.addWidget(self.titleText)
        layout.addWidget(self.subtitleText)
        layout.addSpacing(18)
        layout.addWidget(self.startButton, alignment=Qt.AlignHCenter)
        layout.addStretch()

        central = DriftingNodes()
        central.setLayout(layout)
        self.setCentralWidget(central)

    # swaps the start screen for the main window
    def open_main_window(self):
        self.main_window = MainWindow()
        self.setCentralWidget(self.main_window)


class MainWindow(QMainWindow):
    progress = Signal(str)

    # builds the layout and starts loading the model
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

        self.restartButton.clicked.connect(self.restart_training)
        self.runButton.clicked.connect(self.run_session)
        self.historySlider.valueChanged.connect(self.show_history)
        self.progress.connect(self.show_message)

        self.restart_training()

    # makes all the settings boxes and buttons, they get placed in the build functions
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

        self.restartButton = QPushButton("Restart Training")
        self.runButton = QPushButton("Run Session")

        self.historyLabel = QLabel("History 0/0")
        self.historySlider = QSlider(Qt.Horizontal)
        self.historySlider.setRange(0, 0)

        self.nodeInfo = QLabel()
        self.nodeInfo.setWordWrap(True)
        self.nodeInfo.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.countLabel = QLabel("Nodes: 0\nConnections: 0")




    # graph on top and the terminal log under it
    def build_left_side(self):
        layout = QVBoxLayout()

        self.titleLabel = QLabel(" Node Graph ")
        layout.addWidget(self.titleLabel)

        self.graphArea = graph.Graph3D()
        self.graphArea.setObjectName("graphArea")
        self.graphArea.moved.connect(nodeSystem.hoverRay)
        nodeSystem.onSelect = self.nodeInfo.setText
        nodeSystem.onCount = lambda nodes, conns: self.countLabel.setText(f"Nodes: {nodes}\nConnections: {conns}")
        layout.addWidget(self.graphArea, 3)



        self.terminalLabel = QLabel(" Terminal ")
        layout.addWidget(self.terminalLabel)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

        return layout




    # settings button and node info on top, history slider and run buttons on the bottom
    def build_sidebar(self):
        self.settingsButton = QPushButton("Settings")

        self.settingsButton.setCheckable(True)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(sidebar)

        layout.addWidget(self.settingsButton)
        layout.addWidget(self.nodeInfo, 1)
        layout.addWidget(self.countLabel)
        layout.addWidget(self.historyLabel)
        layout.addWidget(self.historySlider)
        layout.addWidget(self.restartButton)
        layout.addWidget(self.runButton)
        return sidebar

    # the settings panel that slides out next to the sidebar, starts closed
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

    # puts the sidebar, settings panel and graph in a row
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

    # slides the settings panel open or closed
    def slide_settings_panel(self, opening):
        self.panelAnimation.stop()
        self.panelAnimation.setStartValue(self.panelAnimation.targetObject().maximumWidth())
        self.panelAnimation.setEndValue(PANEL_WIDTH if opening else 0)
        self.panelAnimation.start()

    # adds a line to the terminal log
    def show_message(self, text):
        self.log.appendPlainText(text)

    # prints the lesson results and updates the graph with them
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
            graph.loadGraph(self.experiment.facts, self.experiment.links)
            nodeSystem.drawNodes(self.graphArea)
            graph.saveHistory()
            self.graphBuilt = True

        newConfidence = {fact["fact_id"]: fact["confidence"] * 100 for fact in result["facts"]}
        newStrengths = {(row["from_fact"], row["to_fact"]): row["dependency"] * 100 for row in result["links"]}
        graph.updateNodes(newConfidence)
        graph.updateConnections(newStrengths)
        nodeSystem.showNodes()
        nodeSystem.showConnections()
        graph.saveHistory()

        self.historySlider.setMaximum(len(graph.history) - 1)
        self.historySlider.setValue(self.historySlider.maximum())

        # nothing left to run after the last lesson
        if result["lesson"] >= AI.N_LESSONS:
            self.runButton.hide()
            self.show_message("Training has finished. Press Restart Training to go again.")

    # shows the graph from an earlier lesson when you move the slider
    def show_history(self, value):
        nodeSystem.readHistory(value)
        self.historyLabel.setText(f"History {value}/{self.historySlider.maximum()}")

    # throws out the current run and loads a fresh model
    def restart_training(self):
        model = self.modelBox.currentText()
        method = self.methodBox.currentText()
        self.experiment = None
        self.runButton.show()
        self.log.clear()
        nodeSystem.clearGraph()
        self.graphBuilt = False
        self.historySlider.setMaximum(0)
        self.historySlider.setValue(0)
        self.historyLabel.setText("History 0/0")
        self.show_message(f"Loading {model} ({method}). The first time, the model downloads, "
                          f"so this can take a while...")
        self.start_task(AI.Experiment, self.on_experiment_loaded, model, method, self.seedBox.value())

    # the model finished loading so we can start running lessons
    def on_experiment_loaded(self, experiment):
        self.experiment = experiment
        experiment.progress = self.progress.emit
        self.show_message(f"Ready on {experiment.device.upper()}: {experiment.model_name}, "
                          f"{experiment.method}, seed {experiment.seed}.")
        self.show_message(AI.METHOD_TIPS[experiment.method])
        self.show_message("Press Run Session to teach lesson 1.")

    # teaches the next lesson with whatever learning rate and epochs are set
    def run_session(self):
        if self.experiment is None:
            self.show_message("The model isn't loaded yet.")
            return
        self.show_message(f"Teaching lesson {self.experiment.lesson + 1}...")
        self.start_task(self.experiment.teach_next_lesson, self.show_lesson_result,
                        self.learningRateBox.value(), self.epochsBox.value())

    # runs slow stuff in the background so the window doesn't freeze
    def start_task(self, function, on_done, *args):
        self.set_busy(True)
        self.worker = Worker(function, *args)
        self.worker.done.connect(lambda result: self.finish_task(on_done, result))
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    # unlocks the buttons and hands the result over
    def finish_task(self, on_done, result):
        self.set_busy(False)
        on_done(result)

    # unlocks the buttons and prints the error
    def on_failed(self, error):
        self.set_busy(False)
        self.show_message(f"ERROR: {error}")

    # can't press run or restart while something is already running
    def set_busy(self, busy):
        self.runButton.setEnabled(not busy)
        self.restartButton.setEnabled(not busy)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    useFont()
    window = StartWindow()
    window.show()
    code = app.exec()
    # worker threads can't be cancelled and Qt aborts if it destroys one that's running
    os._exit(code)