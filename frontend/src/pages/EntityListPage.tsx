import { useState } from "react";
import { Link } from "react-router-dom";

import { API_URL } from "../api/client";
import { useEntities } from "../hooks/useEntities";

export function EntityListPage() {
  const [typeFilter, setTypeFilter] = useState("");
  const { data: entities, isLoading, error } = useEntities(typeFilter || undefined);

  return (
    <div className="entity-list-page">
      <div className="entity-list-header">
        <h1>Entities</h1>
        <Link to="/entities/new" className="button-primary">
          + New Entity
        </Link>
      </div>

      <input
        placeholder="Filter by type (e.g. npc)"
        value={typeFilter}
        onChange={(e) => setTypeFilter(e.target.value)}
        className="entity-list-filter"
      />

      {isLoading && <p>Loading...</p>}
      {error && <p className="error-text">{(error as Error).message}</p>}

      <ul className="entity-list">
        {entities?.map((entity) => (
          <li key={entity.id}>
            <Link to={`/entities/${entity.id}`} className="entity-list-item">
              {entity.icon ? (
                <img className="entity-list-icon" src={API_URL + entity.icon.url} alt="" />
              ) : (
                <span className="entity-list-icon entity-list-icon-empty" />
              )}
              <span className="entity-type-badge">{entity.type}</span>
              <span className="entity-title">{entity.title}</span>
            </Link>
          </li>
        ))}
      </ul>

      {entities?.length === 0 && <p>No entities yet. Create one to get started.</p>}
    </div>
  );
}
