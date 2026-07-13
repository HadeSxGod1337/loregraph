/** Loading placeholder that mirrors the shape of a list of rows, so the page
 * lays out once instead of jumping from a bare "Loading..." line. */
export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton-list" aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div className="skeleton-row" key={i}>
          <span className="skeleton" style={{ width: 32, height: 32 }} />
          <span className="skeleton-row-lines">
            <span
              className="skeleton"
              style={{ width: `${45 + ((i * 17) % 30)}%`, height: 12 }}
            />
            <span
              className="skeleton"
              style={{ width: `${25 + ((i * 29) % 40)}%`, height: 9 }}
            />
          </span>
        </div>
      ))}
    </div>
  );
}
