import { useState, useEffect } from 'react'
import CalendarHeatmap from 'react-calendar-heatmap'
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { Tooltip as ReactTooltip } from 'react-tooltip'
import 'react-calendar-heatmap/dist/styles.css'
import './App.css'

const NOTES_COLORS = ['#58a6ff', '#39d353', '#d2a8ff']
const OUTPUTS_COLORS = ['#f78166', '#d2a8ff', '#58a6ff']

function App() {
  const [counts, setCounts] = useState({ total_notes: 0, total_outputs: 0 })
  const [heatmapData, setHeatmapData] = useState<any[]>([])
  const [notesComposition, setNotesComposition] = useState<any[]>([])
  const [outputsComposition, setOutputsComposition] = useState<any[]>([])
  const [metrics, setMetrics] = useState<any>(null)
  const [selectedYear, setSelectedYear] = useState(2026)
  const [loading, setLoading] = useState(true)

  // NEW: State to track screen width for responsive inline styles
  const [isMobile, setIsMobile] = useState(window.innerWidth < 768);
  const [isSmallMobile, setIsSmallMobile] = useState(window.innerWidth <= 375);

  useEffect(() => {
    const userId = (window as any).CURRENT_USER_ID;
    
    fetch(`/api/analytics/dashboard-data?user_id=${userId}`)
      .then(res => res.json())
      .then(data => {
        setCounts(data.counts)
        setHeatmapData(data.heatmap)
        setNotesComposition(data.notes_comp)
        setOutputsComposition(data.outputs_comp)
        setMetrics(data.metrics)
        setLoading(false)
      })
      .catch(error => {
        console.error('Error fetching data:', error)
        setLoading(false)
      })

    // NEW: Resize listener to update screen width state
    const handleResize = () => {
      setIsMobile(window.innerWidth < 768);
      setIsSmallMobile(window.innerWidth <= 375);
    };
    
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [])

  if (loading) return <div style={{ padding: '40px', color: '#c9d1d9', textAlign: 'center' }}>Loading...</div>

  const years = [2026, 2025, 2024, 2023, 2022]
  const yearNotes = heatmapData.filter(item => item.date.startsWith(selectedYear.toString())).reduce((sum, item) => sum + item.notes, 0)
  const yearOutputs = heatmapData.filter(item => item.date.startsWith(selectedYear.toString())).reduce((sum, item) => sum + item.outputs, 0)

  // UPDATED: Dynamic styles based on screen width
  const statBoxStyle = {
    backgroundColor: '#161b22',
    border: '1px solid #30363d',
    borderRadius: '6px',
    padding: isSmallMobile ? '6px' : '10px',
    display: 'flex',
    flexDirection: 'column' as const,
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: isSmallMobile ? '60px' : '80px'
  };

  return (
    <div className="dashboard-container-mobile" style={{ width: '100%', maxWidth: '1400px', margin: '-30px auto 0 auto', padding: '20px 16px', boxSizing: 'border-box', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif' }}>
      
      <h1 style={{ marginBottom: '14px', color: '#f0f6fc', fontSize: '20px', fontWeight: 600 }}>Knowledge Base Analytics</h1>
      
      {/* ROW 1: Stats (Dynamic Columns) */}
      <div className="stats-grid-mobile" style={{ 
        display: 'grid', 
        gridTemplateColumns: isSmallMobile ? '1fr' : (isMobile ? 'repeat(2, 1fr)' : 'repeat(4, 1fr)'), 
        gap: isSmallMobile ? '8px' : '16px', 
        marginBottom: '16px' 
      }}>
        
        {/* Box 1: Productivity */}
        <div className="stat-box-mobile" style={statBoxStyle}>
          <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase', marginBottom: '6px' }}>Productivity</div>
          <div style={{ fontSize: '22px', fontWeight: 600, color: '#f0f6fc', marginTop: '2px' }}>{counts.total_notes}</div>
          <div style={{ fontSize: '11px', color: '#8b949e' }}>Notes</div>
          <div style={{ fontSize: '22px', fontWeight: 600, color: '#f0f6fc', marginTop: '2px' }}>{counts.total_outputs}</div>
          <div style={{ fontSize: '11px', color: '#8b949e' }}>Outputs</div>
        </div>

        {/* Box 2: Approval Rate */}
        <div className="stat-box-mobile" style={statBoxStyle}>
          <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase', marginBottom: '8px' }}>Notes Approval Rate</div>
          <div style={{ fontSize: '28px', fontWeight: 600, color: '#39d353' }}>{metrics?.approval_rate || 0}%</div>
        </div>

        {/* Box 3: Total Tokens */}
        <div className="stat-box-mobile" style={statBoxStyle}>
          <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase', marginBottom: '8px' }}>Total Tokens</div>
          <div style={{ fontSize: '28px', fontWeight: 600, color: '#d2a8ff' }}>{metrics?.total_tokens?.toLocaleString() || 0}</div>
        </div>

        {/* Box 4: Avg Tokens */}
        <div className="stat-box-mobile" style={statBoxStyle}>
          <div style={{ fontSize: '11px', color: '#8b949e', textTransform: 'uppercase', marginBottom: '6px' }}>Avg. Tokens</div>
          <div style={{ fontSize: '22px', fontWeight: 600, color: '#58a6ff', marginTop: '2px' }}>{metrics?.avg_tokens_notes || 0}</div>
          <div style={{ fontSize: '11px', color: '#8b949e' }}>Notes</div>
          <div style={{ fontSize: '22px', fontWeight: 600, color: '#f78166', marginTop: '2px' }}>{metrics?.avg_tokens_outputs || 0}</div>
          <div style={{ fontSize: '11px', color: '#8b949e' }}>Outputs</div>
        </div>
      </div>

      {/* ROW 2: Heatmap (Full Width) */}
      <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '16px', borderRadius: '6px', marginBottom: '16px' }}>
        <div style={{ marginBottom: '8px' }}>
          <div style={{ fontSize: '14px', color: '#c9d1d9', fontWeight: 600 }}>Activity Heatmap</div>
          <div style={{ fontSize: '12px', color: '#8b949e', marginTop: '4px' }}>{yearNotes} notes & {yearOutputs} outputs in {selectedYear}</div>
        </div>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, paddingTop: '8px', overflowX: 'auto', minWidth: 0 }}>
            <CalendarHeatmap
              startDate={new Date(`${selectedYear}-01-01`)}
              endDate={new Date(`${selectedYear}-12-31`)}
              values={heatmapData}
              classForValue={(value: any) => {
                if (!value || value.count === 0) return 'color-empty';
                if (value.count <= 2) return 'color-scale-1';
                if (value.count <= 4) return 'color-scale-2';
                if (value.count <= 6) return 'color-scale-3';
                return 'color-scale-4';
              }}
              tooltipDataAttrs={(value: any) => {
                if (!value || !value.date) return {} as any;
                const date = new Date(value.date);
                const formattedDate = date.toLocaleDateString('en-GB', { month: 'short', day: 'numeric', year: 'numeric' });
                return {
                  'data-tooltip-id': 'github-tooltip',
                  'data-tooltip-content': `${value.notes} note${value.notes !== 1 ? 's' : ''} & ${value.outputs} output${value.outputs !== 1 ? 's' : ''} on ${formattedDate}`
                } as any;
              }}
              showWeekdayLabels={true}
            />
          </div>
          
          <div className='year-btn-group' style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '20px' }}>
            {years.map(year => (
              <button 
                key={year} 
                className='year-btn'
                onClick={() => setSelectedYear(year)} 
                style={{ 
                  width: '32px', 
                  height: '20px', 
                  fontSize: '9px', 
                  padding: '0',
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  border: '1px solid #30363d', 
                  borderRadius: '6px', 
                  cursor: 'pointer', 
                  backgroundColor: year === selectedYear ? '#1f6feb' : 'transparent', 
                  color: year === selectedYear ? '#ffffff' : '#c9d1d9', 
                  fontWeight: year === selectedYear ? 600 : 400 
                }}
              >
                {year}
              </button>
            ))}
          </div>

        </div>
        <div className='heatmap-legend'>
          <span>Less</span>
          <div className="legend-box" style={{ backgroundColor: '#161b22', border: '1px solid #30363d' }}></div>
          <div className="legend-box" style={{ backgroundColor: '#0e4429' }}></div>
          <div className="legend-box" style={{ backgroundColor: '#006d32' }}></div>
          <div className="legend-box" style={{ backgroundColor: '#26a641' }}></div>
          <div className="legend-box" style={{ backgroundColor: '#39d353' }}></div>
          <span>More</span>
        </div>
      </div>

      {/* ROW 3: Composition Charts (Dynamic Columns) */}
      <div className="charts-grid-mobile" style={{ 
        display: 'grid', 
        gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)', 
        gap: '16px' 
      }}>
        
        {/* Notes Composition */}
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '14px', borderRadius: '6px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: '14px', color: '#c9d1d9', fontWeight: 600, marginBottom: '8px', textAlign: 'center' }}>Notes Composition</div>
          <div style={{ flex: 1, minHeight: '160px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={notesComposition} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={2} dataKey="value" stroke="none">
                  {notesComposition.map((_, index) => (<Cell key={`cell-n-${index}`} fill={NOTES_COLORS[index % NOTES_COLORS.length]} />))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: '#24292f', border: '1px solid #30363d', borderRadius: '6px', color: '#f0f6fc', fontSize: '11px' }} itemStyle={{ color: '#f0f6fc', fontSize: '11px' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '8px', flexWrap: 'wrap' }}>
            {notesComposition.map((entry, index) => (
              <div key={entry.name} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: '#c9d1d9' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: NOTES_COLORS[index] }}></div>
                {entry.name} ({entry.value})
              </div>
            ))}
          </div>
        </div>

        {/* Outputs Composition */}
        <div style={{ backgroundColor: '#161b22', border: '1px solid #30363d', padding: '14px', borderRadius: '6px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: '14px', color: '#c9d1d9', fontWeight: 600, marginBottom: '8px', textAlign: 'center' }}>Outputs Composition</div>
          <div style={{ flex: 1, minHeight: '160px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={outputsComposition} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={2} dataKey="value" stroke="none">
                  {outputsComposition.map((_, index) => (<Cell key={`cell-o-${index}`} fill={OUTPUTS_COLORS[index % OUTPUTS_COLORS.length]} />))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: '#24292f', border: '1px solid #30363d', borderRadius: '6px', color: '#f0f6fc', fontSize: '11px' }} itemStyle={{ color: '#f0f6fc', fontSize: '11px' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '8px', flexWrap: 'wrap' }}>
            {outputsComposition.map((entry, index) => (
              <div key={entry.name} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: '#c9d1d9' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '2px', backgroundColor: OUTPUTS_COLORS[index] }}></div>
                {entry.name} ({entry.value})
              </div>
            ))}
          </div>
        </div>

      </div>

      <ReactTooltip id="github-tooltip" style={{ backgroundColor: '#24292f', color: '#ffffff', fontSize: '11px', borderRadius: '6px', padding: '4px 8px' }} />
    </div>
  )
}

export default App