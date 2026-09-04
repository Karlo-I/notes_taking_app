import { useState, useEffect } from 'react'
import CalendarHeatmap from 'react-calendar-heatmap'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { Tooltip as ReactTooltip } from 'react-tooltip'
import 'react-calendar-heatmap/dist/styles.css'
import './App.css'

interface ResurfacedThought {
  content: string
  created_at: string | null
  note_type: string | null
}

interface HeatmapValue {
  date: string
  count: number
}

interface CompositionData {
  name: string
  value: number
}

interface QualityMetrics {
  total_sessions: number
  approval_rate: number
  avg_turns: number
  avg_tokens: number
}

// GitHub-style colors for the chart
const CHART_COLORS = ['#58a6ff', '#39d353', '#d2a8ff']

function App() {
  const [totalNotes, setTotalNotes] = useState<number | null>(null)
  const [thought, setThought] = useState<ResurfacedThought | null>(null)
  const [heatmapData, setHeatmapData] = useState<HeatmapValue[]>([])
  const [compositionData, setCompositionData] = useState<CompositionData[]>([])
  const [selectedYear, setSelectedYear] = useState(2026)
  const [loading, setLoading] = useState(true)
  const [qualityMetrics, setQualityMetrics] = useState<QualityMetrics | null>(null)

  useEffect(() => {
    Promise.all([
      fetch('http://127.0.0.1:5000/api/analytics/total-notes').then(res => res.json()),
      fetch('http://127.0.0.1:5000/api/analytics/resurfaced-thought').then(res => res.json()),
      fetch('http://127.0.0.1:5000/api/analytics/heatmap-data').then(res => res.json()),
      fetch('http://127.0.0.1:5000/api/analytics/composition-data').then(res => res.json()),
      fetch('http://127.0.0.1:5000/api/analytics/quality-metrics').then(res => res.json())
    ]).then(([notesData, thoughtData, heatmap, composition, metrics]) => {
      setTotalNotes(notesData.total_notes)
      setThought(thoughtData)
      setHeatmapData(heatmap)
      setCompositionData(composition)
      setQualityMetrics(metrics)
      setLoading(false)
    }).catch(error => {
      console.error('Error fetching data:', error)
      setLoading(false)
    })
  }, [])

  if (loading) return <div style={{ padding: '40px', color: '#c9d1d9', textAlign: 'center' }}>Loading Analytics...</div>

  const years = [2026, 2025, 2024, 2023, 2022]
  
  const yearContributions = heatmapData
    .filter(item => item.date.startsWith(selectedYear.toString()))
    .reduce((sum, item) => sum + item.count, 0)

  return (
    <div style={{ padding: '32px', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif', width: '1100px', margin: '0 auto', boxSizing: 'border-box' }}>
      <h1 style={{ marginBottom: '24px', color: '#f0f6fc', fontSize: '24px', fontWeight: 600 }}>Knowledge Base Analytics</h1>
      
      {/* Resurfaced Thought */}
      {thought && (
        <div style={{ 
          backgroundColor: '#161b22', 
          border: '1px solid #30363d',
          borderLeft: '3px solid #58a6ff', 
          padding: '16px', 
          borderRadius: '6px', 
          marginBottom: '24px',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <span style={{ fontWeight: 600, color: '#58a6ff', textTransform: 'uppercase', fontSize: '12px', letterSpacing: '0.5px' }}>
              Resurfaced Thought
            </span>
            {thought.note_type && (
              <span style={{ 
                backgroundColor: '#1f6feb', 
                color: '#ffffff', 
                padding: '2px 8px', 
                borderRadius: '12px', 
                fontSize: '12px',
                fontWeight: 600,
                textTransform: 'capitalize'
              }}>
                {thought.note_type}
              </span>
            )}
          </div>
          <p style={{ fontSize: '14px', lineHeight: '1.5', color: '#c9d1d9', margin: '0 0 8px 0', whiteSpace: 'pre-wrap' }}>
            {thought.content}
          </p>
          {thought.created_at && (
            <p style={{ fontSize: '12px', color: '#8b949e', margin: 0 }}>
              {new Date(thought.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </p>
          )}
        </div>
      )}

      {/* Heatmap Section */}
      <div style={{ 
        backgroundColor: '#161b22', 
        border: '1px solid #30363d',
        padding: '24px', 
        borderRadius: '6px', 
        marginBottom: '24px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
          <div>
            <h2 style={{ margin: 0, fontSize: '14px', color: '#c9d1d9', fontWeight: 400 }}>Activity Heatmap</h2>
            <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#8b949e' }}>
              {yearContributions} notes in {selectedYear}
            </p>
          </div>
        </div>
        
        <div style={{ display: 'flex', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, minWidth: 0, overflowX: 'auto', paddingTop: '20px' }}>
            <CalendarHeatmap
              startDate={new Date(`${selectedYear}-01-01`)}
              endDate={new Date(`${selectedYear}-12-31`)}
              values={heatmapData}
              classForValue={(value) => {
                if (!value || value.count === 0) return 'color-empty';
                if (value.count === 1) return 'color-scale-1';
                if (value.count === 2) return 'color-scale-2';
                if (value.count === 3) return 'color-scale-3';
                return 'color-scale-4';
              }}
              tooltipDataAttrs={(value) => {
                if (!value || !value.date) return {};
                const date = new Date(value.date);
                const formattedDate = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                return {
                  'data-tooltip-id': 'github-tooltip',
                  'data-tooltip-content': `${value.count} note${value.count !== 1 ? 's' : ''} on ${formattedDate}.`
                };
              }}
              showWeekdayLabels={true}
            />
          </div>
          
          <div className="year-selector-container">
            {years.map(year => (
              <button
                key={year}
                className={`year-button ${year === selectedYear ? 'active' : ''}`}
                onClick={() => setSelectedYear(year)}
              >
                {year}
              </button>
            ))}
          </div>
        </div>

        <div className="heatmap-legend">
          <span>Less</span>
          <div className="legend-box" style={{ backgroundColor: '#161b22' }}></div>
          <div className="legend-box" style={{ backgroundColor: '#0e4429' }}></div>
          <div className="legend-box" style={{ backgroundColor: '#006d32' }}></div>
          <div className="legend-box" style={{ backgroundColor: '#26a641' }}></div>
          <div className="legend-box" style={{ backgroundColor: '#39d353' }}></div>
          <span>More</span>
        </div>
      </div>

      {/* Bottom Grid: Total Notes + Donut Chart */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        
        {/* Total Notes Card */}
        <div style={{ 
          backgroundColor: '#161b22', 
          border: '1px solid #30363d',
          padding: '24px', 
          borderRadius: '6px', 
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <h3 style={{ margin: '0 0 8px 0', color: '#8b949e', fontSize: '12px', textTransform: 'uppercase', fontWeight: 400 }}>Total Notes</h3>
          <p style={{ fontSize: '48px', fontWeight: 600, margin: 0, color: '#f0f6fc' }}>
            {totalNotes}
          </p>
        </div>

        {/* Knowledge Composition (Donut Chart) */}
        <div style={{ 
          backgroundColor: '#161b22', 
          border: '1px solid #30363d',
          padding: '24px', 
          borderRadius: '6px', 
        }}>
          <h3 style={{ margin: '0 0 16px 0', color: '#8b949e', fontSize: '12px', textTransform: 'uppercase', fontWeight: 400, textAlign: 'center' }}>
            Knowledge Composition
          </h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={compositionData}
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={80}
                paddingAngle={2}
                dataKey="value"
                stroke="none"
              >
                {compositionData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ backgroundColor: '#24292f', border: '1px solid #30363d', borderRadius: '6px', color: '#f0f6fc' }}
                itemStyle={{ color: '#f0f6fc' }}
              />
            </PieChart>
          </ResponsiveContainer>
          
          {/* Custom Legend */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '8px' }}>
            {compositionData.map((entry, index) => (
              <div key={entry.name} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#c9d1d9' }}>
                <div style={{ width: '10px', height: '10px', borderRadius: '2px', backgroundColor: CHART_COLORS[index] }}></div>
                {entry.name} ({entry.value})
              </div>
            ))}
          </div>
        </div>

      </div>

      {/* Heatmap Tooltip */}
      <ReactTooltip 
        id="github-tooltip" 
        style={{ 
          backgroundColor: '#24292f', 
          color: '#ffffff', 
          fontSize: '12px', 
          borderRadius: '6px', 
          padding: '6px 10px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
        }} 
      />

      {/* Thinking Quality Metrics Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px', marginTop: '24px' }}>
        
        {/* Card 1: Avg. Tokens per Critique */}
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '24px', borderRadius: '6px', textAlign: 'center' }}>
          <h3 style={{ margin: '0 0 8px 0', color: '#8b949e', fontSize: '12px', textTransform: 'uppercase', fontWeight: 400 }}>Avg. Tokens per Critique</h3>
          <p style={{ fontSize: '36px', fontWeight: 600, margin: 0, color: '#d2a8ff' }}>
            {qualityMetrics?.avg_tokens || 0}
          </p>
        </div>

        {/* Card 2: Approval Rate */}
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '24px', borderRadius: '6px', textAlign: 'center' }}>
          <h3 style={{ margin: '0 0 8px 0', color: '#8b949e', fontSize: '12px', textTransform: 'uppercase', fontWeight: 400 }}>Approval Rate</h3>
          <p style={{ fontSize: '36px', fontWeight: 600, margin: 0, color: '#39d353' }}>
            {qualityMetrics?.approval_rate || 0}%
          </p>
        </div>

        {/* Card 3: Avg. Dialogue Turns */}
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '24px', borderRadius: '6px', textAlign: 'center' }}>
          <h3 style={{ margin: '0 0 8px 0', color: '#8b949e', fontSize: '12px', textTransform: 'uppercase', fontWeight: 400 }}>Avg. Dialogue Turns</h3>
          <p style={{ fontSize: '36px', fontWeight: 600, margin: 0, color: '#58a6ff' }}>
            {qualityMetrics?.avg_turns || 0}
          </p>
        </div>

      </div>

    </div>
  )
}

export default App