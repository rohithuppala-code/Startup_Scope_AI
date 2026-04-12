import React, { useState } from 'react';

export default function InputForm({ onSubmit, isLoading }) {
  const [formData, setFormData] = useState({
    description: '',
    target_market: '',
    business_model: '',
    budget_constraints: ''
  });

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit(formData);
  };

  return (
    <div className="w-full max-w-2xl mx-auto backdrop-blur-lg bg-white/10 dark:bg-black/30 border border-white/20 dark:border-gray-800 rounded-3xl p-8 shadow-2xl transition-all">
      <div className="mb-8 text-center">
        <h2 className="text-3xl font-bold bg-gradient-to-r from-purple-500 to-indigo-500 bg-clip-text text-transparent mb-2">Validate Your Idea</h2>
        <p className="text-gray-500 dark:text-gray-400">Describe your startup, and let our AI VC analyst do the heavy lifting.</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6 text-left">
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Idea Description <span className="text-red-500">*</span></label>
          <textarea 
            required
            name="description"
            value={formData.description}
            onChange={handleChange}
            placeholder="e.g. An AI-powered app that schedules gym sessions based on muscle fatigue."
            className="w-full min-h-[120px] p-4 bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-purple-500 outline-none text-gray-800 dark:text-white transition-all resize-y"
          />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Target Market</label>
            <input 
              type="text"
              name="target_market"
              value={formData.target_market}
              onChange={handleChange}
              placeholder="e.g. College students, SaaS businesses"
              className="w-full p-4 bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-purple-500 outline-none text-gray-800 dark:text-white transition-all"
            />
          </div>

          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Business Model</label>
            <input 
              type="text"
              name="business_model"
              value={formData.business_model}
              onChange={handleChange}
              placeholder="e.g. B2C Subscription, B2B SaaS"
              className="w-full p-4 bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-purple-500 outline-none text-gray-800 dark:text-white transition-all"
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Budget / Constraints</label>
          <input 
            type="text"
            name="budget_constraints"
            value={formData.budget_constraints}
            onChange={handleChange}
            placeholder="e.g. Bootstrapped, $5k initial budget"
            className="w-full p-4 bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700 rounded-xl focus:ring-2 focus:ring-purple-500 outline-none text-gray-800 dark:text-white transition-all"
          />
        </div>

        <button 
          type="submit" 
          disabled={isLoading}
          className={`w-full py-4 mt-6 rounded-xl font-semibold text-white shadow-lg transition-all ${isLoading ? 'bg-gray-400 cursor-not-allowed' : 'bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 hover:-translate-y-1 hover:shadow-purple-500/30'}`}
        >
          {isLoading ? (
            <div className="flex items-center justify-center space-x-2">
              <span className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
              <span>Validating Idea (Takes 15-30s)...</span>
            </div>
          ) : 'Run Deep Analytics & Scrape Web'}
        </button>
      </form>
    </div>
  );
}
