import React, { useEffect, useRef, useState } from 'react';

// Duplicate of the type in page.tsx to avoid complex refactors
export type Segment = {
    id: string;
    content: string;
    translated?: string;
    isPolished: boolean;
    isPartial?: boolean;
};

interface TeleprompterViewProps {
    segments: Segment[];
}

export default function TeleprompterView({ segments }: TeleprompterViewProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [activeIndex, setActiveIndex] = useState<number>(-1);
    const itemRefs = useRef<(HTMLDivElement | null)[]>([]);

    // Update active index when segments change
    useEffect(() => {
        if (segments.length > 0) {
            // Check if the last segment is finalized (not partial) to move focus
            // Or just follow the stream. For teleprompter, usually we follow the stream.
            // In 'alignment' mode, 'segments' will be populated from the imported script, 
            // and we might need an 'activeId' prop to know which one is current.
            // BUT, based on current logic, 'segments' array grows as we receive data.
            // Wait, in alignment mode, we might want to display the WHOLE script and scroll?
            // Currently, page.tsx appends segments as they come in.
            // If it's alignment, we are receiving ALIGNED segments one by one (or as they are matched).
            // So segments array IS the history of matched segments.
            // Thus, the last one is the current one.
            setActiveIndex(segments.length - 1);
        } else {
            setActiveIndex(-1);
        }
    }, [segments]);

    // Center Focus Scroll Logic
    useEffect(() => {
        if (activeIndex >= 0 && itemRefs.current[activeIndex]) {
            itemRefs.current[activeIndex]?.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
                inline: 'center'
            });
        }
    }, [activeIndex]);

    // If no segments, show waiting state
    if (segments.length === 0) {
        return (
            <div className="flex-1 flex items-center justify-center h-full">
                <div className="text-2xl text-white/50 font-light animate-pulse">
                    Waiting for speech...
                </div>
            </div>
        );
    }

    return (
        <div 
            ref={containerRef}
            className="flex-1 flex flex-col h-full w-full overflow-y-auto [&::-webkit-scrollbar]:hidden scroll-smooth relative"
            style={{
                perspective: '1000px', // For 3D effects if needed
                maskImage: 'linear-gradient(to bottom, transparent 0%, black 20%, black 80%, transparent 100%)',
                WebkitMaskImage: 'linear-gradient(to bottom, transparent 0%, black 20%, black 80%, transparent 100%)'
            }}
        >
            <div className="flex flex-col items-center py-[50vh]"> {/* Padding to allow centering first/last items */}
                {segments.map((segment, index) => {
                    const isActive = index === activeIndex;
                    const distance = Math.abs(index - activeIndex);
                    const isNear = distance <= 2;
                    
                    // Visual Enhancement Logic based on distance from active
                    // Active: Full Opacity, Larger, Bright Yellow
                    // Near: Partial Opacity, Normal Size
                    // Far: Low Opacity, Smaller
                    
                    let opacity = 0.3;
                    let scale = 0.9;
                    let color = 'text-white';
                    let fontWeight = 'font-normal';

                    if (isActive) {
                        opacity = 1;
                        scale = 1.1; // Slight pop
                        color = 'text-yellow-400'; // High contrast for dark adaptation
                        fontWeight = 'font-bold';
                    } else if (isNear) {
                        opacity = 0.6;
                        scale = 1.0;
                        color = 'text-white/80';
                    }

                    return (
                        <div
                            key={segment.id}
                            ref={el => { itemRefs.current[index] = el; }} // Assign ref
                            className={`transition-all duration-500 ease-out my-6 max-w-4xl text-center px-4 ${fontWeight}`}
                            style={{
                                opacity,
                                transform: `scale(${scale})`,
                                // Blur effect for non-active items to reduce distraction
                                filter: isActive ? 'none' : `blur(${Math.min(distance, 2)}px)`
                            }}
                        >
                            <p 
                                className={`text-3xl md:text-4xl lg:text-5xl leading-tight ${color}`}
                                style={{ 
                                    textShadow: isActive ? '0 0 20px rgba(250, 204, 21, 0.4)' : 'none' 
                                }}
                            >
                                {segment.content}
                            </p>
                            {segment.translated && (
                                <p className={`text-xl md:text-2xl mt-2 font-light ${isActive ? 'text-yellow-200/90' : 'text-white/60'}`}>
                                    {segment.translated}
                                </p>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
