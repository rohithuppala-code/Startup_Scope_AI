import { useState, useEffect } from 'react'
import InputForm from './components/InputForm'
import ReportView from './components/ReportView'
import ValidationTimeline from './components/ValidationTimeline'
import AuthForm from './components/AuthForm'

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState('');
  const [validationData, setValidationData] = useState(null);
  const [error, setError] = useState(null);
  const [userId, setUserId] = useState(localStorage.getItem('ss_user_id') || null);
  const [showTimeline, setShowTimeline] = useState(false);

  const handleValidate = async (formData) => {
    setIsLoading(true);
    setLoadingStatus('Queueing idea for analysis...');
    setError(null);
    try {
      const response = await fetch('http://localhost:8005/validate-idea', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          idea: formData
        })
      });

      if (!response.ok) {
        throw new Error('API Request failed. Ensure backend and Celery workers are running.');
      }

      const queueData = await response.json();
      setLoadingStatus('Agents are analyzing market & scraping data...');
      
      const validationId = queueData.validation_id;
      let isCompleted = false;
      let attempts = 0;

      while (!isCompleted && attempts < 120) { 
        await new Promise(resolve => setTimeout(resolve, 2000));
        attempts++;

        const pollRes = await fetch(`http://localhost:8005/api/analytics/timeline/${validationId}`);
        if (!pollRes.ok) continue;

        const currentData = await pollRes.json();
        
        if (currentData.status === 'processing') {
          setLoadingStatus('Compiling research and assessing feasibility (this can take 30s)...');
        } else if (currentData.status === 'completed') {
          isCompleted = true;
          setValidationData(currentData);
        } else if (currentData.status === 'failed') {
          throw new Error('Task execution failed: ' + (currentData.competitor_analysis || 'Unknown error'));
        }
      }

      if (!isCompleted) {
        throw new Error('Validation timed out. The agents might still be working in the background.');
      }

    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setIsLoading(false);
      setLoadingStatus('');
    }
  };

  const handleSignOut = () => {
    localStorage.removeItem('ss_user_id');
    localStorage.removeItem('ss_access_token');
    setUserId(null);
    setValidationData(null);
    setShowTimeline(false);
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-[#0a0a0a] text-gray-900 dark:text-gray-100 font-sans selection:bg-purple-500/30">
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] opacity-30 dark:opacity-20 pointer-events-none blur-[120px] rounded-full bg-gradient-to-br from-purple-600 to-blue-600 z-0"></div>

      <div className="relative z-10 container mx-auto px-4 py-8 flex flex-col items-center justify-center min-h-screen">
        
        <header className="text-center mb-12 w-full">
          <div className="flex justify-between items-start w-full max-w-5xl mx-auto mb-8">
            <div className="w-24"></div> {/* Spacer */}
            <div>
              <h1 className="text-5xl font-extrabold tracking-tight mb-4 flex items-center justify-center">
                Startup<span className="text-purple-500">Scope</span> AI
              </h1>
              <p className="text-lg text-gray-600 dark:text-gray-400 max-w-xl mx-auto">
                The world's most brutal, real-time AI Venture Capitalist. Stop guessing. Start validating.
              </p>
            </div>
            <div className="w-24 flex justify-end">
              {userId && (
                <button
                  onClick={handleSignOut}
                  className="text-sm font-medium text-gray-500 hover:text-red-500 dark:text-gray-400 dark:hover:text-red-400 transition-colors"
                >
                  Sign Out
                </button>
              )}
            </div>
          </div>
          
          {userId && !isLoading && (
            <button
              onClick={() => {
                setShowTimeline(!showTimeline);
                setValidationData(null);
              }}
              className="px-6 py-2 bg-white/10 hover:bg-white/20 border border-purple-500/30 text-purple-400 rounded-lg font-medium transition-colors"
            >
              {showTimeline ? 'New Validation' : 'View History'}
            </button>
          )}
        </header>

        {error && (
          <div className="w-full max-w-2xl mb-8 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 rounded-xl text-center">
            {error}
          </div>
        )}

        {/* View Switcher based on Auth */}
        {!userId ? (
          <AuthForm onAuthSuccess={(id) => setUserId(id)} />
        ) : showTimeline ? (
          <div className="w-full max-w-4xl">
            <ValidationTimeline userId={userId} onViewReport={(report) => {
              setValidationData(report);
              setShowTimeline(false);
            }} />
          </div>
        ) : !validationData ? (
          <InputForm onSubmit={handleValidate} isLoading={isLoading} loadingStatus={loadingStatus} />
        ) : (
          <ReportView report={validationData} onReset={() => setValidationData(null)} />
        )}
        
      </div>
    </div>
  )
}

export default App
