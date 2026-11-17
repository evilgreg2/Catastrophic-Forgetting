import math
import random

nodes = {}
connections = {}
history = []
factInfo = {}

# Layout Settings
nodeBuffer = 60
columnSpacing = 160
rowSpacing = 110


def farEnough(x, y):
    for other in nodes.values():
        if math.hypot(x - other["x"], y - other["y"]) < nodeBuffer:
            return False
    return True


def loadGraph(facts, links, width, height):
    topics = []
    placed = {}
    for fact in facts:
        if fact["topic"] not in topics:
            topics.append(fact["topic"])
    lessons = max(f["lesson"] for f in facts)

    # spread the grid over the whole window, margin keeps it off the edges
    margin = 110
    columnSpacing = (width - margin * 2) / max(len(topics) - 1, 1)
    rowSpacing = (height - margin * 2) / max(lessons - 1, 1)

    for fact in facts:
        cell = (fact["topic"], fact["lesson"])
        offset = placed.get(cell, 0)
        placed[cell] = offset + 1
        baseX = margin + topics.index(fact["topic"]) * columnSpacing + offset * 40
        baseY = margin + (fact["lesson"] - 1) * rowSpacing + offset * 40
        for tries in range(100):
            spread = 35 + tries
            x = baseX + random.randint(-spread, spread)
            y = baseY + random.randint(-spread, spread)
            if farEnough(x, y):
                break
        nodes[fact["id"]] = {"x": x, "y": y, "confidence": 0, "taught": False}
        factInfo[fact["id"]] = {"text": fact["questions"][0] + " " + fact["answer"], "topic": fact["topic"], "lesson": fact["lesson"]}

    for pair in links:
        connections[tuple(pair)] = 0


# Saves a copy of all node data and all connection strengths to history
def saveHistory():
    history.append({
        "nodes": {name: dict(data) for name, data in nodes.items()},
        "connections": dict(connections),
    })
