import { useState } from 'react'
import InputForm from './components/InputForm'
import ReportView from './components/ReportView'

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [validationData, setValidationData] = useState(null);
  const [error, setError] = useState(null);

  const handleValidate = async (formData) => {
    setIsLoading(true);
    setError(null);
    try {
      // Basic mock setup to connect to our FastAPI backend
      const response = await fetch('http://localhost:8000/validate-idea', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          idea: {
            idea_id: "session_" + Math.random().toString(36).substr(2, 9),
            ...formData
          }
        })
      });

      if (!response.ok) {
        throw new Error('API Request failed. Make sure the backend is running and API keys are set.');
      }

      const data = await response.json();
      setValidationData(data.report);
      // Notice we are ignoring data.markdown_report for the UI currently, as we use structured parts.

    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 dark:bg-[#0a0a0a] text-gray-900 dark:text-gray-100 font-sans selection:bg-purple-500/30">
      
      {/* Decorative Blob */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] opacity-30 dark:opacity-20 pointer-events-none blur-[120px] rounded-full bg-gradient-to-br from-purple-600 to-blue-600 z-0"></div>

      <div className="relative z-10 container mx-auto px-4 py-16 flex flex-col items-center justify-center min-h-screen">
        
        {/* Header */}
        <header className="text-center mb-12">
          <h1 className="text-5xl font-extrabold tracking-tight mb-4 flex items-center justify-center">
            Startup<span className="text-purple-500">Scope</span> AI
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400 max-w-xl mx-auto">
            The world's most brutal, real-time AI Venture Capitalist. Stop guessing. Start validating.
          </p>
        </header>

        {/* Error State */}
        {error && (
          <div className="w-full max-w-2xl mb-8 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 rounded-xl text-center">
            {error}
          </div>
        )}

        {/* View Switcher */}
        {!validationData ? (
          <InputForm onSubmit={handleValidate} isLoading={isLoading} />
        ) : (
          <ReportView report={validationData} onReset={() => setValidationData(null)} />
        )}
        
      </div>
    </div>
  )
}

export default App
