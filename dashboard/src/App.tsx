import { useState, useEffect } from 'react'
import CalendarHeatmap from 'react-calendar-heatmap'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { Tooltip as ReactTooltip } from 'react-tooltip'
import 'react-calendar-heatmap/dist/styles.css'
import './App.css'

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

const CHART_COLORS = ['#58a6ff', '#39d353', '#d2a8ff']

function App() {
  const [totalNotes, setTotalNotes] = useState<number | null>(null)
  const [heatmapData, setHeatmapData] = useState<HeatmapValue[]>([])
  const [compositionData, setCompositionData] = useState<CompositionData[]>([])
  const [qualityMetrics, setQualityMetrics] = useState<QualityMetrics | null>(null)
  const [selectedYear, setSelectedYear] = useState(2026)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('http://127.0.0.1:5000/api/analytics/total-notes').then(res => res.json()),
      fetch('http://127.0.0.1:5000/api/analytics/heatmap-data').then(res => res.json()),
      fetch('http://127.0.0.1:5000/api/analytics/composition-data').then(res => res.json()),
      fetch('http://127.0.0.1:5000/api/analytics/quality-metrics').then(res => res.json())
    ]).then(([notesData, heatmap, composition, metrics]) => {
      setTotalNotes(notesData.total_notes)
      setHeatmapData(heatmap)
      setCompositionData(composition)
      setQualityMetrics(metrics)
      setLoading(false)
    }).catch(error => {
      console.error('Error fetching data:', error)
      setLoading(false)
    })
  }, [])

  if (loading) return <div style={{ padding: '40px', color: '#c9d1d9', textAlign: 'center' }}>Loading...</div>

  const years = [2026, 2025, 2024, 2023, 2022]
  const yearContributions = heatmapData
    .filter(item => item.date.startsWith(selectedYear.toString()))
    .reduce((sum, item) => sum + item.count, 0)

  return (
    <div style={{ 
      width: '100%', 
      maxWidth: '1400px', 
      margin: '0 auto', 
      padding: '20px 40px', 
      boxSizing: 'border-box',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif' 
    }}>
      <h1 style={{ marginBottom: '24px', color: '#f0f6fc', fontSize: '20px', fontWeight: 600 }}>Knowledge Base Analytics</h1>
      
      {/* Stats Row - 4 Columns */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '16px' }}>
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '16px', borderRadius: '6px', textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase', marginBottom: '8px' }}>Total Notes</div>
          <div style={{ fontSize: '24px', fontWeight: 600, color: '#f0f6fc' }}>{totalNotes}</div>
        </div>
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '16px', borderRadius: '6px', textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase', marginBottom: '8px' }}>Approval Rate</div>
          <div style={{ fontSize: '24px', fontWeight: 600, color: '#39d353' }}>{qualityMetrics?.approval_rate || 0}%</div>
        </div>
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '16px', borderRadius: '6px', textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase', marginBottom: '8px' }}>Avg. Turns</div>
          <div style={{ fontSize: '24px', fontWeight: 600, color: '#58a6ff' }}>{qualityMetrics?.avg_turns || 0}</div>
        </div>
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '16px', borderRadius: '6px', textAlign: 'center' }}>
          <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase', marginBottom: '8px' }}>Avg. Tokens</div>
          <div style={{ fontSize: '24px', fontWeight: 600, color: '#d2a8ff' }}>{qualityMetrics?.avg_tokens || 0}</div>
        </div>
      </div>

      {/* Main Content Row - Responsive Grid using CSS classes */}
      <div className="dashboard-grid">
        
        {/* Heatmap Card */}
        <div className="heatmap-card" style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '16px', borderRadius: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
            <div>
              <div style={{ fontSize: '14px', color: '#c9d1d9', fontWeight: 600 }}>Activity Heatmap</div>
              <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '4px' }}>{yearContributions} notes in {selectedYear}</div>
            </div>
          </div>
          
          <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
            <div style={{ flex: 1, paddingTop: '10px', overflowX: 'auto' }}>
              <CalendarHeatmap
                startDate={new Date(`${selectedYear}-01-01`)}
                endDate={new Date(`${selectedYear}-12-31`)}
                values={heatmapData}
                classForValue={(value: any) => {
                  if (!value || value.count === 0) return 'color-empty';
                  if (value.count === 1) return 'color-scale-1';
                  if (value.count === 2) return 'color-scale-2';
                  if (value.count === 3) return 'color-scale-3';
                  return 'color-scale-4';
                }}
                tooltipDataAttrs={(value: any) => {
                  if (!value || !value.date) return {} as any;
                  const date = new Date(value.date);
                  const formattedDate = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                  return {
                    'data-tooltip-id': 'github-tooltip',
                    'data-tooltip-content': `${value.count} note${value.count !== 1 ? 's' : ''} on ${formattedDate}.`
                  } as any;
                }}
                showWeekdayLabels={true}
              />
            </div>
            
            {/* Year selector on the RIGHT side */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '20px' }}>
              {years.map(year => (
                <button
                  key={year}
                  onClick={() => setSelectedYear(year)}
                  style={{
                    padding: '4px 8px',
                    fontSize: '11px',
                    width: '50px',
                    border: '1px solid #30363d',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    backgroundColor: year === selectedYear ? '#1f6feb' : 'transparent',
                    color: year === selectedYear ? '#ffffff' : '#c9d1d9',
                    fontWeight: year === selectedYear ? 600 : 400,
                  }}
                >
                  {year}
                </button>
              ))}
            </div>
          </div>
          
          <div style={{ marginTop: '16px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '11px', color: '#8b949e' }}>Less</span>
            <div style={{ width: '10px', height: '10px', borderRadius: '2px', backgroundColor: '#161b22', border: '1px solid #30363d' }}></div>
            <div style={{ width: '10px', height: '10px', borderRadius: '2px', backgroundColor: '#0e4429' }}></div>
            <div style={{ width: '10px', height: '10px', borderRadius: '2px', backgroundColor: '#006d32' }}></div>
            <div style={{ width: '10px', height: '10px', borderRadius: '2px', backgroundColor: '#26a641' }}></div>
            <div style={{ width: '10px', height: '10px', borderRadius: '2px', backgroundColor: '#39d353' }}></div>
            <span style={{ fontSize: '11px', color: '#8b949e' }}>More</span>
          </div>
        </div>

        {/* Donut Chart Card */}
        <div className="donut-card" style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '16px', borderRadius: '6px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: '14px', color: '#c9d1d9', fontWeight: 600, marginBottom: '16px', textAlign: 'center' }}>
            Knowledge Composition
          </div>
          <div style={{ flex: 1, minHeight: '200px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={compositionData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={70}
                  paddingAngle={2}
                  dataKey="value"
                  stroke="none"
                >
                  {compositionData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip 
                  contentStyle={{ backgroundColor: '#24292f', border: '1px solid #30363d', borderRadius: '6px', color: '#f0f6fc', fontSize: '11px' }}
                  itemStyle={{ color: '#f0f6fc', fontSize: '11px' }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          
          <div style={{ 
            display: 'flex', 
            justifyContent: 'center', 
            gap: '12px', 
            marginTop: '16px',
            flexWrap: 'wrap',  /* Allows wrapping to next line */
            minHeight: '30px'  /* Ensures consistent height */
          }}>
            {compositionData.map((entry, index) => (
              <div key={entry.name} style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: '6px', 
                fontSize: '11px', 
                color: '#c9d1d9',
                whiteSpace: 'nowrap'  /* Prevents text from breaking mid-word */
              }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: CHART_COLORS[index] }}></div>
                {entry.name} ({entry.value})
              </div>
            ))}
        </div>
        </div>
      </div>

      <ReactTooltip 
        id="github-tooltip" 
        style={{ 
          backgroundColor: '#24292f', 
          color: '#ffffff', 
          fontSize: '11px', 
          borderRadius: '6px', 
          padding: '4px 8px',
        }} 
      />
    </div>
  )
}

export default App