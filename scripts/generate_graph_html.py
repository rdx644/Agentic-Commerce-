import sqlite3
import json
from pathlib import Path

def generate_html(db_path, html_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Fetch nodes
    cursor.execute("SELECT id, type, name FROM nodes")
    nodes = [{'id': row[0], 'group': 1 if row[1]=='module' else (2 if row[1]=='class' else 3), 'type': row[1], 'name': row[2]} for row in cursor.fetchall()]
    
    # Fetch edges
    cursor.execute("SELECT source, target, relationship FROM edges")
    links = [{'source': row[0], 'target': row[1], 'type': row[2]} for row in cursor.fetchall()]
    
    graph_data = {'nodes': nodes, 'links': links}
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Agentic Commerce - Architecture Graph</title>
    <script src="/dashboard/static/d3.min.js"></script>
    <style>
        body {{ margin: 0; background: #0a0a0f; color: #fff; font-family: 'Inter', sans-serif; overflow: hidden; }}
        svg {{ width: 100vw; height: 100vh; }}
        .node circle {{ stroke: #fff; stroke-width: 1.5px; }}
        .link {{ stroke: #555570; stroke-opacity: 0.6; }}
        .label {{ font-size: 10px; fill: #8888a0; pointer-events: none; }}
        #info-panel {{ position: absolute; top: 20px; left: 20px; background: rgba(20,20,35,0.9); padding: 15px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.1); width: 300px; }}
        h1 {{ font-size: 16px; margin: 0 0 10px 0; color: #4d7cff; }}
        .legend {{ margin-top: 15px; font-size: 12px; }}
        .legend-item {{ display: flex; align-items: center; margin-bottom: 5px; }}
        .legend-color {{ width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }}
    </style>
</head>
<body>
    <div id="info-panel">
        <h1>Architecture Graph</h1>
        <p style="font-size: 12px; color: #8888a0;">Drag nodes to explore. Scroll to zoom.</p>
        <div id="selected-node" style="margin-top: 15px; font-size: 13px;">
            Hover over a node to see details.
        </div>
        <div class="legend">
            <div class="legend-item"><div class="legend-color" style="background:#4d7cff"></div>Module</div>
            <div class="legend-item"><div class="legend-color" style="background:#34d399"></div>Class</div>
            <div class="legend-item"><div class="legend-color" style="background:#f87171"></div>Function</div>
        </div>
    </div>
    <svg></svg>

    <script>
        const graph = {json.dumps(graph_data)};
        
        const width = window.innerWidth;
        const height = window.innerHeight;

        const svg = d3.select("svg")
            .call(d3.zoom().on("zoom", (event) => {{
                g.attr("transform", event.transform);
            }}));
            
        const g = svg.append("g");

        const color = d3.scaleOrdinal()
            .domain([1, 2, 3])
            .range(["#4d7cff", "#34d399", "#f87171"]);

        const simulation = d3.forceSimulation(graph.nodes)
            .force("link", d3.forceLink(graph.links).id(d => d.id).distance(50))
            .force("charge", d3.forceManyBody().strength(-150))
            .force("center", d3.forceCenter(width / 2, height / 2))
            .force("collide", d3.forceCollide().radius(20));

        const link = g.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(graph.links)
            .join("line")
            .attr("class", "link")
            .attr("stroke-width", d => d.type === 'IMPORTS' ? 2 : 1)
            .style("stroke-dasharray", d => d.type === 'IMPORTS' ? "none" : "3,3");

        const node = g.append("g")
            .attr("class", "nodes")
            .selectAll("g")
            .data(graph.nodes)
            .join("g")
            .attr("class", "node")
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));

        node.append("circle")
            .attr("r", d => d.group === 1 ? 8 : (d.group === 2 ? 6 : 4))
            .attr("fill", d => color(d.group));

        node.append("text")
            .attr("class", "label")
            .attr("dx", 12)
            .attr("dy", 4)
            .text(d => d.name)
            .style("display", d => d.group === 1 ? "block" : "none");

        // Show/hide labels on hover and update info panel
        node.on("mouseover", function(event, d) {{
            d3.select(this).select("text").style("display", "block");
            
            // Find connected links
            const connectedLinks = graph.links.filter(l => l.source.id === d.id || l.target.id === d.id);
            const importedBy = connectedLinks.filter(l => l.target.id === d.id && l.type === 'IMPORTS').map(l => l.source.name);
            const imports = connectedLinks.filter(l => l.source.id === d.id && l.type === 'IMPORTS').map(l => l.target.name);
            
            const container = document.getElementById("selected-node");
            const frag = document.createDocumentFragment();

            const title = document.createElement("strong");
            title.textContent = d.name;
            frag.appendChild(title);
            frag.appendChild(document.createElement("br"));

            const typeSpan = document.createElement("span");
            typeSpan.style.color = "#8888a0";
            typeSpan.style.fontSize = "11px";
            typeSpan.textContent = d.type.toUpperCase();
            frag.appendChild(typeSpan);
            frag.appendChild(document.createElement("br"));
            frag.appendChild(document.createElement("br"));

            const idDiv = document.createElement("div");
            idDiv.style.fontSize = "11px";
            idDiv.style.wordWrap = "break-word";
            idDiv.textContent = d.id;
            frag.appendChild(idDiv);

            if (imports.length > 0) {{
                frag.appendChild(document.createElement("br"));
                const impStrong = document.createElement("strong");
                impStrong.textContent = "Imports: ";
                frag.appendChild(impStrong);
                frag.appendChild(document.createTextNode(imports.join(", ")));
            }}

            if (importedBy.length > 0) {{
                frag.appendChild(document.createElement("br"));
                const impByStrong = document.createElement("strong");
                impByStrong.textContent = "Imported by: ";
                frag.appendChild(impByStrong);
                frag.appendChild(document.createTextNode(importedBy.join(", ")));
            }}

            container.replaceChildren(frag);
        }})
        .on("mouseout", function(event, d) {{
            if (d.group !== 1) {{
                d3.select(this).select("text").style("display", "none");
            }}
            document.getElementById("selected-node").textContent = "Hover over a node to see details.";
        }});

        simulation.on("tick", () => {{
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node
                .attr("transform", d => `translate(${{d.x}},${{d.y}})`);
        }});

        function dragstarted(event, d) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }}

        function dragged(event, d) {{
            d.fx = event.x;
            d.fy = event.y;
        }}

        function dragended(event, d) {{
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }}
    </script>
</body>
</html>"""
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Generated HTML visualization at {html_path}")

if __name__ == "__main__":
    db_path = Path(r"C:\Users\putit\agentic-commerce\architecture_graph.db")
    html_path = Path(r"C:\Users\putit\agentic-commerce\architecture_graph.html")
    generate_html(db_path, html_path)
