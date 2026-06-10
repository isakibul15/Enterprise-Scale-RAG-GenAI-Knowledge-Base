import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Virtual scrolling hook for rendering large lists efficiently.
 * Only renders visible messages + buffer items.
 * Reduces DOM nodes from 10k to ~50, improving performance dramatically.
 */
export function useVirtualScroll({
  items = [],
  itemHeight = 80,
  bufferSize = 5,
  containerHeight = 600,
}) {
  const scrollRef = useRef(null);
  const [scrollTop, setScrollTop] = useState(0);

  // Calculate visible range
  const visibleCount = Math.ceil(containerHeight / itemHeight) + bufferSize * 2;
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - bufferSize);
  const endIndex = Math.min(items.length, startIndex + visibleCount);

  // Calculate offset for virtual container
  const offsetY = startIndex * itemHeight;
  const visibleItems = items.slice(startIndex, endIndex);
  const totalHeight = items.length * itemHeight;

  const handleScroll = useCallback((e) => {
    setScrollTop(e.target.scrollTop);
  }, []);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [handleScroll]);

  return {
    scrollRef,
    visibleItems,
    startIndex,
    offsetY,
    totalHeight,
    containerHeight,
    itemHeight,
  };
}

/**
 * Virtual list component wrapper
 */
export function VirtualList({
  items,
  renderItem,
  itemHeight = 80,
  bufferSize = 5,
  className = '',
  containerHeight = 600,
}) {
  const {
    scrollRef,
    visibleItems,
    startIndex,
    offsetY,
    totalHeight,
  } = useVirtualScroll({
    items,
    itemHeight,
    bufferSize,
    containerHeight,
  });

  return (
    <div
      ref={scrollRef}
      className={`overflow-y-auto ${className}`}
      style={{
        height: containerHeight,
        position: 'relative',
      }}
    >
      <div
        style={{
          height: totalHeight,
          position: 'relative',
        }}
      >
        <div
          style={{
            transform: `translateY(${offsetY}px)`,
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
          }}
        >
          {visibleItems.map((item, idx) => (
            <div
              key={startIndex + idx}
              style={{
                height: itemHeight,
                marginBottom: 0,
              }}
            >
              {renderItem(item, startIndex + idx)}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
