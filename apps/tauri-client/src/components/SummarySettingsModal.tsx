'use client';

import { useState, useEffect } from 'react';
import { X } from 'lucide-react';

interface SummarySettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
    meetingId: string;
    currentTemplate: string;
    onGenerateSummary: (options: { template: string, context: string, length: string, style: string }) => void;
    generatingSummary: boolean;
}

export function SummarySettingsModal({
    isOpen,
    onClose,
    meetingId,
    currentTemplate,
    onGenerateSummary,
    generatingSummary
}: SummarySettingsModalProps) {
    const [template, setTemplate] = useState(currentTemplate);
    const [customContext, setCustomContext] = useState('');
    const [summaryLength, setSummaryLength] = useState('medium'); // short, medium, long
    const [summaryStyle, setSummaryStyle] = useState('formal');   // formal, casual

    useEffect(() => {
        setTemplate(currentTemplate); // Sync template if it changes from parent
    }, [currentTemplate]);

    if (!isOpen) return null;

    const handleGenerateClick = () => {
        onGenerateSummary({
            template: template,
            context: customContext,
            length: summaryLength,
            style: summaryStyle,
        });
        onClose(); // Close modal after triggering generation
    };

    return (
        <div className="fixed inset-0 z-[101] flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="bg-neutral-800/95 border border-white/10 rounded-lg shadow-xl w-full max-w-lg p-6 text-white">
                <div className="flex justify-between items-center mb-4">
                    <h2 className="text-xl font-bold">Generate Summary Settings</h2>
                    <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-full transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="space-y-4">
                    {/* Template Selection */}
                    <div>
                        <label htmlFor="template" className="block text-sm font-medium text-gray-300 mb-1">Summary Template</label>
                        <select
                            id="template"
                            value={template}
                            onChange={(e) => setTemplate(e.target.value)}
                            className="w-full bg-neutral-700 border border-neutral-600 rounded-md p-2 text-white text-sm focus:ring-blue-500 focus:border-blue-500"
                            disabled={generatingSummary}
                        >
                            <option value="general">General</option>
                            <option value="sales_bant">Sales (BANT)</option>
                            <option value="hr_star">HR (STAR)</option>
                            <option value="tech">Tech (Decision)</option>
                        </select>
                    </div>

                    {/* Custom Context / Keywords */}
                    <div>
                        <label htmlFor="customContext" className="block text-sm font-medium text-gray-300 mb-1">Additional Context / Keywords (Optional)</label>
                        <textarea
                            id="customContext"
                            value={customContext}
                            onChange={(e) => setCustomContext(e.target.value)}
                            rows={3}
                            placeholder="e.g., John Doe is CEO, discuss Q3 earnings, focus on AI strategy."
                            className="w-full bg-neutral-700 border border-neutral-600 rounded-md p-2 text-white text-sm focus:ring-blue-500 focus:border-blue-500 resize-y"
                            disabled={generatingSummary}
                        ></textarea>
                        <p className="text-xs text-gray-400 mt-1">These will be used to guide the LLM during summarization.</p>
                    </div>

                    {/* Summary Length */}
                    <div>
                        <label className="block text-sm font-medium text-gray-300 mb-1">Summary Length</label>
                        <div className="flex space-x-2">
                            {['short', 'medium', 'long'].map((len) => (
                                <button
                                    key={len}
                                    onClick={() => setSummaryLength(len)}
                                    className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${summaryLength === len ? 'bg-blue-600 text-white' : 'bg-neutral-700 text-gray-300 hover:bg-neutral-600'}`}
                                    disabled={generatingSummary}
                                >
                                    {len.charAt(0).toUpperCase() + len.slice(1)}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Summary Style */}
                    <div>
                        <label className="block text-sm font-medium text-gray-300 mb-1">Summary Style</label>
                        <div className="flex space-x-2">
                            {['formal', 'casual'].map((style) => (
                                <button
                                    key={style}
                                    onClick={() => setSummaryStyle(style)}
                                    className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${summaryStyle === style ? 'bg-blue-600 text-white' : 'bg-neutral-700 text-gray-300 hover:bg-neutral-600'}`}
                                    disabled={generatingSummary}
                                >
                                    {style.charAt(0).toUpperCase() + style.slice(1)}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Generate Button */}
                    <button
                        onClick={handleGenerateClick}
                        disabled={generatingSummary}
                        className="w-full py-2 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
                    >
                        {generatingSummary ? 'Generating...' : 'Generate Summary'}
                    </button>
                </div>
            </div>
        </div>
    );
}
