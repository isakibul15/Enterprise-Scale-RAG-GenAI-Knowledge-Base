export function MessageSkeleton() {
  return (
    <div className="flex gap-3 animate-pulse">
      {/* Avatar skeleton */}
      <div
        className="w-7 h-7 rounded-lg flex-shrink-0"
        style={{ background: 'rgba(124, 58, 237, 0.1)' }}
      />

      {/* Message skeleton */}
      <div className="flex-1 space-y-2">
        <div
          className="h-4 rounded w-3/4"
          style={{ background: 'rgba(124, 58, 237, 0.1)' }}
        />
        <div
          className="h-4 rounded w-5/6"
          style={{ background: 'rgba(124, 58, 237, 0.1)' }}
        />
        <div
          className="h-4 rounded w-4/6"
          style={{ background: 'rgba(124, 58, 237, 0.1)' }}
        />
      </div>
    </div>
  );
}

export function ChatSkeleton() {
  return (
    <div className="space-y-6 p-4">
      <MessageSkeleton />
      <div className="flex gap-3 animate-pulse flex-row-reverse">
        <div
          className="w-7 h-7 rounded-lg flex-shrink-0"
          style={{ background: 'rgba(124, 58, 237, 0.1)' }}
        />
        <div className="flex-1 space-y-2">
          <div
            className="h-4 rounded w-2/3"
            style={{ background: 'rgba(124, 58, 237, 0.1)' }}
          />
          <div
            className="h-4 rounded w-3/4"
            style={{ background: 'rgba(124, 58, 237, 0.1)' }}
          />
        </div>
      </div>
    </div>
  );
}
