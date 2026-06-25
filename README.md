# ♟️ Chess Openings Manager

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0.0-green.svg" alt="Flask">
  <img src="https://img.shields.io/badge/Memgraph-2.14+-orange.svg" alt="Memgraph">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="MIT License">
</p>

<p align="center">
  <strong>Interactive Chess Openings Explorer powered by Memgraph</strong>
</p>

---

## 📖 Overview

**Chess Openings Manager** is an interactive web application designed to explore, detect, and analyze chess openings using a **Memgraph graph database**.

The application combines:

* **Flask** for the backend API
* **Memgraph** for graph storage and Cypher querying
* **Chess.js** and **Chessboard.js** for chessboard interactions
* **Vis.js** for graph visualization

It demonstrates how graph databases can efficiently model complex relationships between chess openings, ECO families, and move similarities.

---

## 🎯 Project Goals

* Automatically detect openings from a chess position.
* Explore relationships between openings using graph structures.
* Visualize opening networks interactively.
* Execute advanced Cypher graph queries.
* Demonstrate graph database concepts through a real-world chess dataset.

---

## ✨ Features

### ♟️ Interactive Chessboard

* Drag-and-drop chess pieces.
* Real-time opening detection.
* Position analysis using FEN notation.

### 📚 Openings Library

* Paginated openings list.
* Search by name, ECO code, or variant.
* ECO family filtering (A–E).

### 🔍 Opening Details

* Opening metadata.
* FEN position preview.
* Move sequence visualization.
* Similar openings discovery.

### 🌐 Graph Visualization

* Interactive graph powered by Vis.js.
* Explore opening relationships.
* Highlight connected openings and clusters.

### 📡 REST API

* Complete CRUD operations.
* Opening detection endpoint.
* Search and similarity queries.
* Statistics and graph data endpoints.

### 🚀 Memgraph Integration

* Native Cypher queries.
* Graph traversals.
* Shortest path computations.
* Similarity relationship analysis.

---

## 🏗️ Technical Stack

| Layer               | Technology              |
| ------------------- | ----------------------- |
| Backend             | Flask 3.x               |
| Database            | Memgraph                |
| Driver              | Neo4j Python Driver     |
| Frontend            | HTML5, Bootstrap 5, CSS |
| Chess Engine        | Chess.js                |
| Chessboard UI       | Chessboard.js           |
| Graph Visualization | Vis.js                  |
| Containerization    | Docker & Docker Compose |
| Language            | Python 3.10+            |

---

## 📁 Project Structure

```text
brahim-mekkaoui-chess-memgraph/
├── app.py
├── config.py
├── docker-compose.yml
├── import_data.py
├── models.py
├── requirements.txt
│
├── data/
│   └── openings_eco.json
│
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
│
├── templates/
│   ├── index.html
│   ├── openings_list.html
│   ├── opening_detail.html
│   └── graph_view.html
│
└── utils/
    └── fen_utils.py
```

---

## ⚙️ Installation

### Prerequisites

* Docker
* Docker Compose

Required ports:

| Service      | Port |
| ------------ | ---- |
| Flask        | 5000 |
| Memgraph     | 7687 |
| Memgraph Lab | 3000 |

---

### 1️⃣ Clone Repository

```bash
git clone https://github.com/Brahim-Mekkaoui/Chess-Memgraph.git
cd Chess-Memgraph
```

### 2️⃣ Start Containers

```bash
docker-compose up -d
```

Services launched:

* Flask → http://localhost:5000
* Memgraph → bolt://localhost:7687
* Memgraph Lab → http://localhost:3000

---

### 3️⃣ Import Dataset

```bash
docker exec -it chess_app python import_data.py
```

The import script:

* Clears existing data
* Creates indexes
* Imports 125 ECO openings
* Creates `SIMILAR_TO` relationships

---

### 4️⃣ Open Application

Navigate to:

```text
http://localhost:5000
```

Use the interactive chessboard to detect openings in real time.

---

## 🧪 Sample Cypher Queries

### Openings from ECO Family B

```cypher
MATCH (o:Opening)
WHERE o.eco_code STARTS WITH 'B'
RETURN o.name, o.eco_code
ORDER BY o.eco_code
```

### Similar Openings

```cypher
MATCH (o:Opening {eco_code:'C97'})-[r:SIMILAR_TO]-(s)
RETURN o.name AS source, s.name AS similar
```

### Top Connected Openings

```cypher
MATCH (o:Opening)-[r:SIMILAR_TO]-()
RETURN o.name, count(r) AS degree
ORDER BY degree DESC
LIMIT 5
```

### Shortest Path Between Openings

```cypher
MATCH p = shortestPath(
 (a:Opening {eco_code:'C00'})-[:SIMILAR_TO*]-
 (b:Opening {eco_code:'D30'})
)
RETURN [n IN nodes(p) | n.eco_code] AS path
```

---

## 📡 REST API

### System

| Method | Endpoint      | Description                |
| ------ | ------------- | -------------------------- |
| GET    | `/api/status` | Memgraph connection status |
| GET    | `/api/stats`  | Graph statistics           |

### Openings

| Method | Endpoint            |
| ------ | ------------------- |
| GET    | `/api/openings`     |
| GET    | `/api/opening/<id>` |
| POST   | `/api/opening`      |
| PUT    | `/api/opening/<id>` |
| DELETE | `/api/opening/<id>` |

### Search & Analysis

| Method | Endpoint                   |
| ------ | -------------------------- |
| GET    | `/api/detect?fen=`         |
| GET    | `/api/search?q=`           |
| GET    | `/api/moves?moves=`        |
| GET    | `/api/similar/<id>?depth=` |
| GET    | `/api/graph-data`          |

---

### Example Request

```bash
curl -X POST http://localhost:5000/api/opening \
-H "Content-Type: application/json" \
-d '{
  "name":"Grob Attack",
  "eco_code":"A00",
  "moves":"1. g4",
  "variant":"Irregular Opening"
}'
```

---

## 🖥️ User Interface

### Home Page

* Interactive chessboard
* Real-time opening detection
* Similar openings panel
* Statistics dashboard

### Openings Library

* Opening cards
* Search and filters
* CRUD operations

### Opening Detail

* FEN preview
* Annotated moves
* Similar openings
* Neighborhood graph

### Graph Explorer

* Interactive network visualization
* ECO filtering
* Node information panel
* Educational Cypher examples

---

## 🔧 Configuration

Environment variables used by Docker:

```env
MEMGRAPH_HOST=memgraph
MEMGRAPH_PORT=7687
FLASK_DEBUG=True
```

---

## 🛠️ Customization

### Add New Openings

Use:

* UI forms
* `POST /api/opening`

Relationships are generated automatically when openings share:

* The same ECO family
* The first two moves

### Create New Relationship Types

Extend:

```python
_create_similar_relations_for()
```

Examples:

* `TRANSPOSES_TO`
* `LEADS_TO`
* `COUNTERS`

### Modify Similarity Logic

Edit:

```python
are_similar()
```

inside:

```text
import_data.py
```

---

## 🤝 Contributing

Contributions are welcome.

Potential improvements:

* Opening detection algorithms
* Dataset enrichment
* UI/UX enhancements
* Additional Cypher examples
* Advanced graph analytics

### Workflow

```bash
git checkout -b feature/my-feature
git commit -m "Add new feature"
git push origin feature/my-feature
```

Then open a Pull Request.

---


##

<p align="center">
♟️ Happy Chess Analysis!
</p>
