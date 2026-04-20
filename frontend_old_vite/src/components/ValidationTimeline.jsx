import React, { useState, useEffect } from 'react';

export default function ValidationTimeline({ userId, onViewReport }) {
  const [validations, setValidations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    if (userId) {
      fetchValidations();
    }
  }, [userId]);

  const fetchValidations = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `http://localhost:8005/api/analytics/timeline?user_id=${userId}&limit=50`
      );
      
      if (!response.ok) {
        throw new Error('Failed to fetch validation history');
      }
      
      const data = await response.json();
      setValidations(data.validations);
    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const getFeasibilityColor = (score) => {
    if (score >= 70) return 'from-green-400 to-emerald-600';
    if (score >= 40) return 'from-yellow-400 to-orange-500';
    return 'from-red-400 to-rose-600';
  };

  const formatDate = (timestamp) => {
    return new Date(timestamp).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="w-8 h-8 border-4 border-purple-500/30 border-t-purple-500 rounded-full animate-spin"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 rounded-xl">
        Error: {error}
      </div>
    );
  }

  if (validations.length === 0) {
    return (
      <div className="text-center p-12">
        <div className="text-6xl mb-4">📊</div>
        <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
          No Validations Yet
        </h3>
        <p className="text-gray-600 dark:text-gray-400">
          Validate your first startup idea to see it appear here!
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
          Validation Timeline
        </h2>
        <span className="text-sm text-gray-500 dark:text-gray-400">
          {validations.length} validation{validations.length !== 1 ? 's' : ''}
        </span>
      </div>

      {validations.map((validation) => (
        <div
          key={validation.id}
          className="backdrop-blur-lg bg-white/10 dark:bg-black/30 border border-white/20 dark:border-gray-800 rounded-2xl p-6 shadow-lg transition-all hover:shadow-xl relative"
        >
          {/* Status Badge */}
          {validation.status === 'processing' && (
             <div className="absolute top-4 right-4 bg-yellow-500/20 text-yellow-600 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider flex items-center">
               <span className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse mr-2"></span>
               Processing
             </div>
          )}
          {validation.status === 'queued' && (
             <div className="absolute top-4 right-4 bg-gray-500/20 text-gray-600 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider">
               Queued
             </div>
          )}
          {validation.status === 'failed' && (
             <div className="absolute top-4 right-4 bg-red-500/20 text-red-600 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider">
               Failed
             </div>
          )}

          {/* Header */}
          <div className="flex items-start justify-between mb-4 mt-2">
            <div className="flex-1">
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">
                {formatDate(validation.created_at)}
              </p>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white line-clamp-2">
                {validation.idea_description || "Untitled Idea"}
              </h3>
            </div>
            
            {/* Feasibility Score Badge (only if completed) */}
            {validation.status === 'completed' && (
              <div className="ml-4 flex flex-col items-center mt-2">
                <div className="relative flex items-center justify-center w-16 h-16 rounded-full bg-gradient-to-br from-purple-500/20 to-indigo-500/20 shadow-inner">
                  <span className={`text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r ${getFeasibilityColor(validation.feasibility_score)}`}>
                    {Math.round(validation.feasibility_score || 0)}
                  </span>
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400 mt-1">Score</span>
              </div>
            )}
          </div>

          {/* Top 3 Gaps Preview */}
          {validation.status === 'completed' && validation.identified_gaps && validation.identified_gaps.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Top Identified Gaps:
              </h4>
              <ul className="space-y-1">
                {validation.identified_gaps.slice(0, 3).map((gap, idx) => (
                  <li key={idx} className="flex items-start text-sm text-gray-600 dark:text-gray-400">
                    <span className="text-rose-500 mr-2">•</span>
                    <span className="line-clamp-1">{gap}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Expand/Collapse Button */}
          {validation.status === 'completed' && (
            <div className="flex space-x-2 mt-4">
              <button
                onClick={() => setExpandedId(expandedId === validation.id ? null : validation.id)}
                className="flex-1 py-2 px-4 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg text-sm font-medium transition-colors"
              >
                {expandedId === validation.id ? 'Hide Inline Preview' : 'Preview Details'}
              </button>
              {onViewReport && (
                <button
                  onClick={() => onViewReport(validation)}
                  className="flex-1 py-2 px-4 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  Full Report View
                </button>
              )}
            </div>
          )}

          {/* Expanded Content */}
          {expandedId === validation.id && validation.status === 'completed' && (
            <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700 space-y-6">
              {/* Competitor Analysis */}
              {validation.competitor_analysis && (
                <div>
                  <h4 className="text-sm font-semibold text-indigo-500 mb-2 flex items-center">
                    <span className="bg-indigo-500/10 p-2 rounded-lg mr-2">📊</span>
                    Competitor Analysis
                  </h4>
                  <div className="bg-gray-50 dark:bg-gray-900/50 p-4 rounded-xl text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                    {validation.competitor_analysis}
                  </div>
                </div>
              )}

              {/* All Identified Gaps */}
              {validation.identified_gaps && validation.identified_gaps.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-rose-500 mb-2 flex items-center">
                    <span className="bg-rose-500/10 p-2 rounded-lg mr-2">⚠️</span>
                    All Identified Gaps
                  </h4>
                  <ul className="space-y-2">
                    {validation.identified_gaps.map((gap, idx) => (
                      <li key={idx} className="flex items-start bg-gray-50 dark:bg-gray-900/50 p-3 rounded-lg text-sm">
                        <span className="text-rose-500 mr-2 mt-0.5">•</span>
                        <span className="text-gray-700 dark:text-gray-300">{gap}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Suggested Improvements */}
              {validation.suggested_improvements && validation.suggested_improvements.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-emerald-500 mb-2 flex items-center">
                    <span className="bg-emerald-500/10 p-2 rounded-lg mr-2">💡</span>
                    Suggested Improvements
                  </h4>
                  <ul className="space-y-2">
                    {validation.suggested_improvements.map((improvement, idx) => (
                      <li key={idx} className="flex items-start bg-gray-50 dark:bg-gray-900/50 p-3 rounded-lg text-sm">
                        <span className="text-emerald-500 mr-2 mt-0.5">→</span>
                        <span className="text-gray-700 dark:text-gray-300">{improvement}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
