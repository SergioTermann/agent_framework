"""
因果思维链可视化模块

功能：
1. 因果链路图可视化
2. 推理过程可视化
3. 置信度热力图
4. 导出为多种格式（PNG, SVG, HTML）
"""

from typing import Dict, List, Any, Optional
import agent_framework.core.fast_json as json


class CausalVisualizer:
    """因果可视化器"""

    def __init__(self):
        self.available_backends = self._check_backends()

    def _check_backends(self) -> Dict[str, bool]:
        """检查可用的可视化后端"""
        backends = {}

        try:
            import networkx
            backends["networkx"] = True
        except ImportError:
            backends["networkx"] = False

        try:
            import matplotlib
            backends["matplotlib"] = True
        except ImportError:
            backends["matplotlib"] = False

        try:
            import plotly
            backends["plotly"] = True
        except ImportError:
            backends["plotly"] = False

        return backends

    def visualize_causal_chain(
        self,
        structure: Dict[str, Any],
        output_file: Optional[str] = None,
        format: str = "html",
        interactive: bool = True
    ) -> Optional[str]:
        """
        可视化因果链

        参数：
            structure: 因果结构（从 extract_causal_structure 获得）
            output_file: 输出文件路径
            format: 输出格式 (html, png, svg, json)
            interactive: 是否生成交互式图表

        返回：
            HTML 字符串（如果 format='html' 且 output_file=None）
        """
        links = structure.get("links", [])
        if not links:
            return self._generate_empty_visualization()

        if format == "html" and interactive:
            return self._visualize_with_html(links, output_file)
        elif format == "json":
            return self._export_to_json(structure, output_file)
        elif self.available_backends.get("networkx") and self.available_backends.get("matplotlib"):
            return self._visualize_with_networkx(links, output_file, format)
        else:
            return self._visualize_with_ascii(links)

    def _visualize_with_html(self, links: List[Dict], output_file: Optional[str]) -> str:
        """使用 HTML/CSS 生成交互式可视化"""
        html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>因果链路可视化</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 20px;
            background: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        .chain {
            margin: 30px 0;
        }
        .link {
            display: flex;
            align-items: center;
            margin: 20px 0;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 8px;
            transition: all 0.3s;
        }
        .link:hover {
            background: #e8f5e9;
            transform: translateX(5px);
        }
        .node {
            flex: 1;
            padding: 15px 20px;
            background: #2196F3;
            color: white;
            border-radius: 5px;
            font-weight: bold;
            text-align: center;
        }
        .arrow {
            flex: 0 0 200px;
            text-align: center;
            padding: 0 20px;
        }
        .relation {
            display: block;
            font-size: 14px;
            color: #666;
            margin-bottom: 5px;
        }
        .confidence {
            display: inline-block;
            padding: 4px 12px;
            background: #4CAF50;
            color: white;
            border-radius: 12px;
            font-size: 12px;
            font-weight: bold;
        }
        .confidence.low { background: #f44336; }
        .confidence.medium { background: #FF9800; }
        .confidence.high { background: #4CAF50; }
        .stats {
            margin-top: 30px;
            padding: 20px;
            background: #e3f2fd;
            border-radius: 8px;
        }
        .stat-item {
            display: inline-block;
            margin-right: 30px;
            font-size: 14px;
        }
        .stat-label {
            font-weight: bold;
            color: #1976D2;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔗 因果链路可视化</h1>
        <div class="chain">
"""

        # 添加每个链接
        for i, link in enumerate(links, 1):
            confidence = link.get("confidence", 0.0)
            conf_class = "high" if confidence >= 0.7 else ("medium" if confidence >= 0.4 else "low")

            html += f"""
            <div class="link">
                <div class="node">{link.get('source', 'Unknown')}</div>
                <div class="arrow">
                    <span class="relation">{link.get('relation', '→')}</span>
                    <span class="confidence {conf_class}">{confidence:.2f}</span>
                </div>
                <div class="node">{link.get('target', 'Unknown')}</div>
            </div>
"""

        # 添加统计信息
        avg_confidence = sum(l.get("confidence", 0) for l in links) / len(links) if links else 0
        html += f"""
        </div>
        <div class="stats">
            <div class="stat-item">
                <span class="stat-label">链接数量:</span> {len(links)}
            </div>
            <div class="stat-item">
                <span class="stat-label">平均置信度:</span> {avg_confidence:.2f}
            </div>
            <div class="stat-item">
                <span class="stat-label">生成时间:</span> {self._get_timestamp()}
            </div>
        </div>
    </div>
</body>
</html>
"""

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            return None
        else:
            return html

    def _visualize_with_networkx(
        self,
        links: List[Dict],
        output_file: Optional[str],
        format: str
    ) -> Optional[str]:
        """使用 NetworkX 和 Matplotlib 生成图表"""
        try:
            import networkx as nx
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches

            # 创建有向图
            G = nx.DiGraph()

            # 添加边
            for link in links:
                source = link.get("source", "")
                target = link.get("target", "")
                relation = link.get("relation", "")
                confidence = link.get("confidence", 0.0)

                G.add_edge(
                    source,
                    target,
                    label=f"{relation}\n{confidence:.2f}",
                    weight=confidence
                )

            # 布局
            pos = nx.spring_layout(G, k=2, iterations=50)

            # 绘图
            plt.figure(figsize=(14, 10))
            plt.title("因果链路图", fontsize=16, fontweight='bold', pad=20)

            # 绘制节点
            nx.draw_networkx_nodes(
                G, pos,
                node_color='lightblue',
                node_size=3000,
                alpha=0.9
            )

            # 绘制边
            edges = G.edges()
            weights = [G[u][v]['weight'] for u, v in edges]

            nx.draw_networkx_edges(
                G, pos,
                width=[w * 3 for w in weights],
                alpha=0.6,
                edge_color=weights,
                edge_cmap=plt.cm.RdYlGn,
                arrows=True,
                arrowsize=20,
                arrowstyle='->'
            )

            # 绘制标签
            nx.draw_networkx_labels(
                G, pos,
                font_size=10,
                font_weight='bold'
            )

            # 绘制边标签
            edge_labels = nx.get_edge_attributes(G, 'label')
            nx.draw_networkx_edge_labels(
                G, pos,
                edge_labels,
                font_size=8
            )

            # 添加图例
            legend_elements = [
                mpatches.Patch(color='green', label='高置信度 (≥0.7)'),
                mpatches.Patch(color='yellow', label='中置信度 (0.4-0.7)'),
                mpatches.Patch(color='red', label='低置信度 (<0.4)')
            ]
            plt.legend(handles=legend_elements, loc='upper right')

            plt.axis('off')
            plt.tight_layout()

            if output_file:
                plt.savefig(output_file, format=format, dpi=300, bbox_inches='tight')
                plt.close()
                return None
            else:
                plt.show()
                return None

        except Exception as e:
            return f"可视化失败: {str(e)}"

    def _visualize_with_ascii(self, links: List[Dict]) -> str:
        """生成 ASCII 文本可视化"""
        output = ["\n" + "="*60]
        output.append("因果链路图 (ASCII)")
        output.append("="*60 + "\n")

        for i, link in enumerate(links, 1):
            source = link.get("source", "Unknown")
            target = link.get("target", "Unknown")
            relation = link.get("relation", "→")
            confidence = link.get("confidence", 0.0)

            output.append(f"{i}. {source}")
            output.append(f"   |")
            output.append(f"   | [{relation}, 置信度: {confidence:.2f}]")
            output.append(f"   ↓")
            output.append(f"   {target}")
            output.append("")

        output.append("="*60)
        return "\n".join(output)

    def _export_to_json(self, structure: Dict[str, Any], output_file: Optional[str]) -> str:
        """导出为 JSON 格式"""
        json_str = json.dumps(structure, ensure_ascii=False, indent=2)

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json_str)
            return None
        else:
            return json_str

    def _generate_empty_visualization(self) -> str:
        """生成空可视化"""
        return """
<html>
<body style="font-family: Arial; padding: 50px; text-align: center;">
    <h2>暂无因果链路数据</h2>
    <p>请先进行因果推理分析</p>
</body>
</html>
"""

    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def generate_reasoning_report(
        self,
        result,  # CausalAnalysisResult
        output_file: Optional[str] = None
    ) -> str:
        """
        生成推理报告

        参数：
            result: CausalAnalysisResult 对象
            output_file: 输出文件路径

        返回：
            HTML 报告字符串
        """
        structure = result.causal_structure

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>因果推理报告</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #1976D2;
            border-bottom: 3px solid #1976D2;
            padding-bottom: 15px;
        }}
        h2 {{
            color: #333;
            margin-top: 30px;
            border-left: 4px solid #4CAF50;
            padding-left: 15px;
        }}
        .meta {{
            background: #e3f2fd;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .meta-item {{
            margin: 10px 0;
        }}
        .label {{
            font-weight: bold;
            color: #1976D2;
            display: inline-block;
            width: 120px;
        }}
        .badge {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 15px;
            font-size: 14px;
            font-weight: bold;
        }}
        .badge.high {{ background: #4CAF50; color: white; }}
        .badge.medium {{ background: #FF9800; color: white; }}
        .badge.low {{ background: #f44336; color: white; }}
        .section {{
            margin: 30px 0;
        }}
        .response {{
            background: #f9f9f9;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #2196F3;
            white-space: pre-wrap;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            line-height: 1.6;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            margin: 10px 0;
        }}
        .stat-label {{
            font-size: 14px;
            opacity: 0.9;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 因果推理分析报告</h1>

        <div class="meta">
            <div class="meta-item">
                <span class="label">查询:</span> {result.query}
            </div>
            <div class="meta-item">
                <span class="label">推理模式:</span> {result.mode.value if result.mode else '自动检测'}
            </div>
            <div class="meta-item">
                <span class="label">检测置信度:</span>
                <span class="badge {'high' if result.confidence >= 0.7 else ('medium' if result.confidence >= 0.4 else 'low')}">
                    {result.confidence:.2f}
                </span>
            </div>
            <div class="meta-item">
                <span class="label">质量评分:</span>
                <span class="badge {'high' if result.quality_score >= 0.7 else ('medium' if result.quality_score >= 0.4 else 'low')}">
                    {result.quality_score:.2f}
                </span>
            </div>
            <div class="meta-item">
                <span class="label">分析时间:</span> {self._format_timestamp(result.timestamp)}
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">因果链接</div>
                <div class="stat-value">{len(structure.get('links', []))}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">假设数量</div>
                <div class="stat-value">{len(structure.get('hypotheses', []))}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">推理步骤</div>
                <div class="stat-value">{len(structure.get('reasoning_steps', []))}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">平均置信度</div>
                <div class="stat-value">{structure.get('confidence', 0):.2f}</div>
            </div>
        </div>

        <h2>🔗 因果链路</h2>
        <div class="section">
            {self._render_links_html(structure.get('links', []))}
        </div>

        <h2>💭 完整推理过程</h2>
        <div class="response">{result.llm_response}</div>
    </div>
</body>
</html>
"""

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            return None
        else:
            return html

    def _render_links_html(self, links: List[Dict]) -> str:
        """渲染链接为 HTML"""
        if not links:
            return "<p>暂无因果链接</p>"

        html_parts = []
        for link in links:
            conf = link.get('confidence', 0)
            conf_class = 'high' if conf >= 0.7 else ('medium' if conf >= 0.4 else 'low')
            html_parts.append(f"""
            <div style="margin: 15px 0; padding: 15px; background: #f9f9f9; border-radius: 5px;">
                <strong>{link.get('source', 'Unknown')}</strong>
                <span style="color: #666; margin: 0 10px;">→ [{link.get('relation', '')}]</span>
                <strong>{link.get('target', 'Unknown')}</strong>
                <span class="badge {conf_class}" style="margin-left: 10px;">{conf:.2f}</span>
            </div>
            """)

        return "".join(html_parts)

    def _format_timestamp(self, timestamp: float) -> str:
        """格式化时间戳"""
        from datetime import datetime
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


# ─── 便捷函数 ──────────────────────────────────────────────────────────────────

def visualize_causal_chain(
    structure: Dict[str, Any],
    output_file: str = "causal_chain.html",
    format: str = "html"
) -> Optional[str]:
    """可视化因果链（便捷函数）"""
    visualizer = CausalVisualizer()
    return visualizer.visualize_causal_chain(structure, output_file, format)


def generate_report(
    result,  # CausalAnalysisResult
    output_file: str = "causal_report.html"
) -> Optional[str]:
    """生成推理报告（便捷函数）"""
    visualizer = CausalVisualizer()
    return visualizer.generate_reasoning_report(result, output_file)
