import { useState, useEffect } from 'react';
import { X, ArrowDown, FileInput, RefreshCw } from 'lucide-react';

export interface ImportedSegment {
    content: string;
    translated?: string;
}

interface ScriptImportModalProps {
    isOpen: boolean;
    onClose: () => void;
    onImport: (segments: ImportedSegment[]) => void;
}

export function ScriptImportModal({
    isOpen,
    onClose,
    onImport
}: ScriptImportModalProps) {
    const [rawText, setRawText] = useState('');
    const [previewSegments, setPreviewSegments] = useState<ImportedSegment[]>([]);
    const [activeTab, setActiveTab] = useState<'input' | 'preview'>('input');

    // Reset state when opening
    useEffect(() => {
        if (isOpen) {
            setRawText('');
            setPreviewSegments([]);
            setActiveTab('input');
        }
    }, [isOpen]);

    if (!isOpen) return null;

    const parseScript = () => {
        const lines = rawText.split(/\r?\n/).map(l => l.trim()).filter(l => l);
        const newSegments: ImportedSegment[] = [];
        
        for (let i = 0; i < lines.length; i++) {
            const current = lines[i];
            const next = lines[i+1];
            
            const isCurrentChinese = /[\u4e00-\u9fa5]/.test(current);
            const isNextChinese = next ? /[\u4e00-\u9fa5]/.test(next) : false;
            
            // Pattern: CN line followed by non-CN line (English)
            if (isCurrentChinese && next && !isNextChinese) {
                newSegments.push({ content: current, translated: next });
                i++; // Skip next line as it's used as translation
            } else {
                newSegments.push({ content: current });
            }
        }
        
        setPreviewSegments(newSegments);
        setActiveTab('preview');
    };

    const handleImport = () => {
        onImport(previewSegments);
        onClose();
    };

    const updateSegment = (index: number, field: 'content' | 'translated', value: string) => {
        const newSegments = [...previewSegments];
        newSegments[index] = { ...newSegments[index], [field]: value };
        setPreviewSegments(newSegments);
    };

    return (
        <div className="fixed inset-0 z-[101] flex items-center justify-center bg-black/70 backdrop-blur-sm">
            <div className="bg-neutral-800/95 border border-white/10 rounded-lg shadow-xl w-full max-w-3xl h-[80vh] flex flex-col text-white">
                {/* Header */}
                <div className="flex justify-between items-center p-6 border-b border-white/10">
                    <div className="flex items-center gap-2">
                        <FileInput className="w-5 h-5 text-blue-400" />
                        <h2 className="text-xl font-bold">Import Script</h2>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-full transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-hidden flex flex-col p-6">
                    {activeTab === 'input' ? (
                        <div className="flex-1 flex flex-col gap-4">
                            <div className="bg-blue-500/10 border border-blue-500/20 rounded-md p-4 text-sm text-blue-200">
                                <p className="font-semibold mb-1">How to use:</p>
                                <p>Paste your script below. The importer will automatically detect Chinese/English pairs.</p>
                                <p className="mt-1 opacity-70">Format: Line 1 (Chinese) → Line 2 (English)</p>
                            </div>
                            <textarea
                                value={rawText}
                                onChange={(e) => setRawText(e.target.value)}
                                placeholder="Paste your script here..."
                                className="flex-1 w-full bg-neutral-900/50 border border-neutral-700 rounded-md p-4 text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none font-mono"
                            />
                        </div>
                    ) : (
                        <div className="flex-1 flex flex-col gap-4 overflow-hidden">
                            <div className="flex justify-between items-center">
                                <h3 className="text-sm font-medium text-gray-300">Preview & Edit ({previewSegments.length} segments)</h3>
                                <button 
                                    onClick={() => setActiveTab('input')}
                                    className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                                >
                                    <RefreshCw className="w-3 h-3" /> Reparse
                                </button>
                            </div>
                            
                            <div className="flex-1 overflow-y-auto custom-scrollbar border border-neutral-700 rounded-md bg-neutral-900/30">
                                <table className="w-full text-sm text-left">
                                    <thead className="text-xs text-gray-400 uppercase bg-neutral-800 sticky top-0 z-10">
                                        <tr>
                                            <th className="px-4 py-3 w-1/2">Content (Original)</th>
                                            <th className="px-4 py-3 w-1/2">Translation</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-neutral-800">
                                        {previewSegments.map((seg, idx) => (
                                            <tr key={idx} className="hover:bg-white/5 group">
                                                <td className="p-2">
                                                    <textarea
                                                        value={seg.content}
                                                        onChange={(e) => updateSegment(idx, 'content', e.target.value)}
                                                        className="w-full bg-transparent border-none focus:ring-0 p-0 text-white resize-none overflow-hidden"
                                                        rows={Math.max(1, Math.ceil(seg.content.length / 40))}
                                                    />
                                                </td>
                                                <td className="p-2">
                                                    <textarea
                                                        value={seg.translated || ''}
                                                        onChange={(e) => updateSegment(idx, 'translated', e.target.value)}
                                                        placeholder="-"
                                                        className="w-full bg-transparent border-none focus:ring-0 p-0 text-gray-300 resize-none overflow-hidden"
                                                        rows={Math.max(1, Math.ceil((seg.translated?.length || 0) / 40))}
                                                    />
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-6 border-t border-white/10 flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 rounded-md text-sm font-medium text-gray-300 hover:bg-white/10 transition-colors"
                    >
                        Cancel
                    </button>
                    {activeTab === 'input' ? (
                        <button
                            onClick={parseScript}
                            disabled={!rawText.trim()}
                            className="px-4 py-2 rounded-md text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                        >
                            Parse Script <ArrowDown className="w-4 h-4" />
                        </button>
                    ) : (
                        <button
                            onClick={handleImport}
                            className="px-4 py-2 rounded-md text-sm font-medium text-white bg-green-600 hover:bg-green-700 transition-colors flex items-center gap-2"
                        >
                            Import {previewSegments.length} Segments
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
