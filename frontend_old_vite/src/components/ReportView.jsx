import React from 'react';

export default function ReportView({ report, markdown, onReset }) {
  if (!report) return null;

  return (
    <div className="w-full max-w-4xl mx-auto backdrop-blur-lg bg-white/10 dark:bg-black/30 border border-white/20 dark:border-gray-800 rounded-3xl p-8 shadow-2xl text-left animate-in fade-in slide-in-from-bottom-8 duration-700">
      <div className="flex items-center justify-between mb-8 border-b border-gray-200 dark:border-gray-800 pb-6">
        <div>
          <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Validation Complete</h2>
          <p className="text-gray-500">Based on real-time competitor data.</p>
        </div>
        <div className="flex flex-col items-center">
          <div className="relative flex items-center justify-center w-24 h-24 rounded-full bg-gradient-to-br from-purple-500/20 to-indigo-500/20 shadow-inner">
            <span className={`text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r ${report.feasibility_score >= 70 ? 'from-green-400 to-emerald-600' : report.feasibility_score >= 40 ? 'from-yellow-400 to-orange-500' : 'from-red-400 to-rose-600'}`}>
              {report.feasibility_score}
            </span>
          </div>
          <span className="text-xs uppercase tracking-widest text-gray-500 mt-2 font-semibold">Feasibility</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
        <div className="space-y-4">
          <h3 className="text-xl font-semibold flex items-center text-rose-500">
            <span className="bg-rose-500/10 p-2 rounded-lg mr-3">⚠️</span> Identified Market Gaps
          </h3>
          <ul className="space-y-3">
            {report.identified_gaps.map((gap, i) => (
              <li key={i} className="flex items-start bg-gray-50 dark:bg-gray-900/50 p-4 rounded-xl border border-gray-100 dark:border-gray-800">
                <span className="text-rose-500 mr-2 mt-0.5">•</span>
                <span className="text-gray-700 dark:text-gray-300">{gap}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="space-y-4">
          <h3 className="text-xl font-semibold flex items-center text-emerald-500">
            <span className="bg-emerald-500/10 p-2 rounded-lg mr-3">💡</span> Suggested Pivots / Next Steps
          </h3>
          <ul className="space-y-3">
            {report.suggested_improvements.map((imp, i) => (
              <li key={i} className="flex items-start bg-gray-50 dark:bg-gray-900/50 p-4 rounded-xl border border-gray-100 dark:border-gray-800">
                <span className="text-emerald-500 mr-2 mt-0.5">→</span>
                <span className="text-gray-700 dark:text-gray-300">{imp}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="space-y-4 mb-8">
        <h3 className="text-xl font-semibold flex items-center text-indigo-500">
          <span className="bg-indigo-500/10 p-2 rounded-lg mr-3">📊</span> Competitor Breakdown
        </h3>
        <div className="bg-gray-50 dark:bg-gray-900/50 p-6 rounded-2xl border border-gray-100 dark:border-gray-800 text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
          {report.competitor_analysis}
        </div>
      </div>

      <button 
        onClick={onReset}
        className="mx-auto block px-8 py-3 bg-gray-200 dark:bg-gray-800 hover:bg-gray-300 dark:hover:bg-gray-700 text-gray-800 dark:text-white rounded-xl font-medium transition-colors"
      >
        Validate Another Idea
      </button>

    </div>
  );
}
