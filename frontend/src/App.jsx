import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Activity, FileText, CheckCircle, UploadCloud, Play, RefreshCw, Search, Folder, Square, Settings, Save, Edit3, Trash2, FileDown, AlertTriangle, Info, X, AlertCircle, RotateCcw, Image, Download } from 'lucide-react';
import logoOriginal from './assets/original.png';
import './index.css';

const API_URL = window.location.origin === 'http://localhost:5173' ? 'http://localhost:5000/api' : '/api';

// Fetch seguro
async function safeFetch(url, options = {}) {
  try {
    const res = await fetch(url, { ...options, signal: AbortSignal.timeout(8000) });
    if (!res.ok) return null;
    const data = await res.json();
    return data;
  } catch {
    return null;
  }
}

function App() {
  const pendingFolderRef = useRef(null);
  const processedFolderRef = useRef(null);
  const isFetchingRef = useRef(false);

  const [stats, setStats] = useState({ pendientes: 0, procesados: 0, erroneos: 0, activo: false, intervalo: 5 });
  const [pendingDocs, setPendingDocs] = useState([]);
  const [processedDocs, setProcessedDocs] = useState([]);
  const [errorDocs, setErrorDocs] = useState([]);
  const [logs, setLogs] = useState([]);
  const [activeTab, setActiveTab] = useState('procesados');
  const [searchTerm, setSearchTerm] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [config, setConfig] = useState({
    ruta_pendientes: '',
    ruta_procesados: '',
    intervalo: 5,
    persistente: false
  });
  const [guardarPermanente, setGuardarPermanente] = useState(true);
  const [modal, setModal] = useState({ show: false, title: '', message: '', type: 'info', onConfirm: null });
  const [backendOff, setBackendOff] = useState(false);
  const logEndRef = useRef(null);

  const fetchData = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    try {
      // Stats
      const statsData = await safeFetch(`${API_URL}/stats`);
      if (statsData && !statsData.error) {
        setBackendOff(false);
        setStats({
          pendientes: Number(statsData.pendientes) || 0,
          procesados: Number(statsData.procesados) || 0,
          erroneos: Number(statsData.erroneos) || 0,
          activo: !!statsData.activo,
          intervalo: Number(statsData.intervalo) || 5
        });
      } else if (statsData === null) {
        setBackendOff(true);
      }

      // Pendientes - Usando el endpoint original
      const pendingData = await safeFetch(`${API_URL}/pending`);
      if (Array.isArray(pendingData)) {
        const safePending = pendingData
          .filter(d => d && typeof d === 'object')
          .map(d => ({
            nombre: String(d.nombre || ''),
            tamaño: String(d.tamaño || d['tama\u00f1o'] || ''),
            fecha: String(d.fecha || '')
          }));
        setPendingDocs(safePending);
      }

      // Procesados - Usando el endpoint original
      const processedData = await safeFetch(`${API_URL}/processed`);
      if (Array.isArray(processedData)) {
        const safeProcessed = processedData
          .filter(d => d && typeof d === 'object')
          .map(d => ({
            nombre: String(d.nombre || d.folio || ''),
            tamaño: String(d.tamaño || ''),
            fecha: String(d.fecha || ''),
            formato: String(d.formato || d.tipo || 'PDF')
          }));
        setProcessedDocs(safeProcessed);
      }

      // Erroneos
      const errorData = await safeFetch(`${API_URL}/errors`);
      if (Array.isArray(errorData)) {
        const safeErrors = errorData
          .filter(e => e && typeof e === 'object')
          .map(e => ({
            nombre: String(e.nombre || ''),
            error: String(e.error || 'Error desconocido'),
            fecha: String(e.fecha || ''),
            tamaño: String(e.tamaño || '')
          }));
        setErrorDocs(safeErrors);
      }

      // Logs
      const logsData = await safeFetch(`${API_URL}/logs`);
      if (logsData && Array.isArray(logsData.logs)) {
        setLogs(logsData.logs.map(String));
      }

      // Config
      if (!showConfig) {
        const cfgData = await safeFetch(`${API_URL}/config`);
        if (cfgData && typeof cfgData === 'object' && !cfgData.error) {
          setConfig({
            ruta_pendientes: String(cfgData.ruta_pendientes || ''),
            ruta_procesados: String(cfgData.ruta_procesados || ''),
            intervalo: Number(cfgData.intervalo) || 5,
            persistente: !!cfgData.persistente
          });
          setGuardarPermanente(!!cfgData.persistente);
          if (!cfgData.ruta_pendientes || !cfgData.ruta_procesados) {
            setShowConfig(true);
          }
        }
      }
    } finally {
      isFetchingRef.current = false;
    }
  }, [showConfig]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Subir imágenes usando el endpoint original /upload
  const handleUpload = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    let uploaded = 0;
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      const result = await safeFetch(`${API_URL}/upload`, { method: 'POST', body: formData });
      if (result !== null) uploaded++;
    }
    
    if (uploaded > 0) {
      setModal({
        show: true,
        title: 'Éxito',
        message: `Se subieron ${uploaded} imágenes correctamente.`,
        type: 'success'
      });
      fetchData();
    }
  };

  // Procesar usando el endpoint original /process
  const handleProcess = async () => {
    try {
      setIsProcessing(true);
      const result = await safeFetch(`${API_URL}/process`, { method: 'POST' });
      if (result !== null) {
        setModal({
          show: true,
          title: 'Procesando',
          message: 'Las imágenes se están convirtiendo a PDF.',
          type: 'info'
        });
      }
    } finally {
      setTimeout(() => {
        setIsProcessing(false);
        fetchData();
      }, 3000);
    }
  };

  const handleRetryError = async (fileName) => {
    setModal({
      show: true,
      title: 'Reintentar Conversión',
      message: `¿Deseas reintentar la conversión de "${fileName}"?`,
      type: 'info',
      onConfirm: async () => {
        await safeFetch(`${API_URL}/retry-error/${encodeURIComponent(fileName)}`, { method: 'POST' });
        fetchData();
      }
    });
  };

  const handleRetryAllErrors = async () => {
    if (errorDocs.length === 0) return;
    setModal({
      show: true,
      title: 'Reintentar Todos',
      message: `¿Deseas reintentar la conversión de todos los documentos erróneos (${errorDocs.length})?`,
      type: 'warning',
      onConfirm: async () => {
        await safeFetch(`${API_URL}/retry-all-errors`, { method: 'POST' });
        fetchData();
      }
    });
  };

  const handleDeleteError = async (fileName) => {
    setModal({
      show: true,
      title: 'Eliminar Documento',
      message: `¿Estás seguro de que deseas eliminar "${fileName}" de la lista de errores?`,
      type: 'warning',
      onConfirm: async () => {
        await safeFetch(`${API_URL}/delete-error/${encodeURIComponent(fileName)}`, { method: 'DELETE' });
        fetchData();
      }
    });
  };

  const handleDownload = async (nombre) => {
    window.open(`${API_URL}/download/${encodeURIComponent(nombre)}`, '_blank');
  };

  const handleOpenFolder = async (nombre) => {
    await safeFetch(`${API_URL}/open/${encodeURIComponent(nombre)}`, { method: 'POST' });
  };

  const handleFolderSelect = (event, key) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      const fullPath = files[0].webkitRelativePath || files[0].name;
      const folderPath = fullPath.split('/').slice(0, -1).join('/').replace(/^\./, '');
      setConfig(prev => ({ ...prev, [key]: folderPath }));
    }
  };

  const handleBrowse = (key) => {
    const refs = {
      ruta_pendientes: pendingFolderRef,
      ruta_procesados: processedFolderRef
    };
    refs[key]?.current?.click();
  };

  const handleSaveConfig = async () => {
    const result = await safeFetch(`${API_URL}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...config, guardar_permanente: guardarPermanente, borrar_permanente: !guardarPermanente }),
    });
    if (result !== null) {
      setModal({ show: true, title: 'Éxito', message: 'Configuración guardada exitosamente.', type: 'success' });
      setShowConfig(false);
      fetchData();
    }
  };

  const handleStop = async () => {
    const result = await safeFetch(`${API_URL}/stop`, { method: 'POST' });
    if (result !== null) {
      setModal({ show: true, title: 'Detención', message: 'Solicitud de detención enviada.', type: 'info' });
    }
  };

  const handleDownloadLogs = () => {
    window.open(`${API_URL}/logs/download`, '_blank');
  };

  const handleClearLogs = () => {
    setModal({
      show: true,
      title: 'Confirmar Limpieza',
      message: '¿Estás seguro de que quieres limpiar el archivo de logs?',
      type: 'warning',
      onConfirm: async () => {
        await safeFetch(`${API_URL}/logs/clear`, { method: 'POST' });
        setLogs([]);
        fetchData();
      }
    });
  };

  const closeModal = () => setModal(prev => ({ ...prev, show: false }));

  const filteredProcessed = processedDocs.filter(doc => {
    const term = searchTerm.toLowerCase();
    return doc.nombre.toLowerCase().includes(term);
  });

  const filteredErrors = errorDocs.filter(error => {
    const term = searchTerm.toLowerCase();
    return error.nombre.toLowerCase().includes(term) || error.error.toLowerCase().includes(term);
  });

  return (
    <div className="app-container">
      <header>
        <div className="header-brand">
          <img src={logoOriginal} alt="Ofilab" className="header-logo" />
          <div>
            <h1>Conversor de Imágenes a PDF</h1>
            <span className="subtitle">
              Sistema de procesamiento documental
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          {backendOff && (
            <span className="offline-badge">
              ⚠ Sin conexión al servidor
            </span>
          )}
          <button
            className="btn-icon"
            title="Configuración"
            onClick={() => setShowConfig(v => !v)}
            style={{ 
              width: '38px', 
              height: '38px', 
              background: showConfig ? 'rgba(46, 32, 150, 0.08)' : 'var(--bg-card)',
              border: showConfig ? '1px solid var(--primary)' : '1px solid var(--border-color)'
            }}
          >
            <Settings size={18} color={showConfig ? 'var(--primary)' : 'var(--text-secondary)'} />
          </button>
          <div className={`status-badge ${stats.activo ? 'active' : 'inactive'}`}>
            <div className="status-dot"></div>
            <span>{stats.activo ? 'Procesando' : 'En Espera'}</span>
            <span className="status-interval">
              (Auto: {stats.intervalo}m)
            </span>
          </div>
        </div>
      </header>

      {showConfig && (
        <div className="glass-card config-panel">
          <h2 className="config-title">
            <Edit3 size={18} /> Configuración de Rutas
          </h2>
          <div className="config-grid">
            {[
              { label: 'Carpeta de Imágenes (Pendientes)', key: 'ruta_pendientes' },
              { label: 'Carpeta de PDFs (Procesados)', key: 'ruta_procesados' },
            ].map(({ label, key }) => (
              <div key={key} className="config-item">
                <label className="config-label">{label}</label>
                <div className="config-input-wrapper">
                  <input
                    className="config-input"
                    value={config[key]}
                    onChange={(e) => setConfig(prev => ({ ...prev, [key]: e.target.value }))}
                    placeholder={`Selecciona la carpeta de ${label.toLowerCase()}`}
                  />
                  <button className="btn-icon" onClick={() => handleBrowse(key)}>
                    <Folder size={16} />
                  </button>
                </div>
              </div>
            ))}
            <div className="config-item">
              <label className="config-label">Intervalo (Minutos)</label>
              <input
                type="number"
                className="config-input"
                value={config.intervalo}
                onChange={(e) => setConfig(prev => ({ ...prev, intervalo: e.target.value }))}
                min="1"
              />
            </div>
          </div>
          <div className="config-checkbox">
            <input
              type="checkbox"
              id="chk-perm"
              checked={guardarPermanente}
              onChange={(e) => setGuardarPermanente(e.target.checked)}
            />
            <label htmlFor="chk-perm">Recordar esta configuración permanentemente</label>
          </div>
          <div className="config-actions">
            <button className="btn btn-secondary" onClick={() => setShowConfig(false)}>Cancelar</button>
            <button className="btn btn-primary" onClick={handleSaveConfig}><Save size={16} /> Guardar Cambios</button>
            <input type="file" webkitdirectory="true" multiple style={{ display: 'none' }} ref={pendingFolderRef} onChange={(e) => handleFolderSelect(e, 'ruta_pendientes')} />
            <input type="file" webkitdirectory="true" multiple style={{ display: 'none' }} ref={processedFolderRef} onChange={(e) => handleFolderSelect(e, 'ruta_procesados')} />
          </div>
        </div>
      )}

      <div className="stats-grid">
        <div className="glass-card stat-card">
          <div className="stat-title"><CheckCircle size={14} className="stat-icon success" />PDFs Generados</div>
          <div className="stat-value success-text">{stats.procesados}</div>
        </div>
        <div className="glass-card stat-card">
          <div className="stat-title"><Image size={14} className="stat-icon warning" />Imágenes Pendientes</div>
          <div className="stat-value warning-text">{stats.pendientes}</div>
        </div>
        <div className="glass-card stat-card">
          <div className="stat-title"><AlertCircle size={14} className="stat-icon danger" />Erróneos</div>
          <div className="stat-value danger-text">{stats.erroneos}</div>
        </div>
        <div className="glass-card stat-card">
          <div className="stat-title"><Activity size={14} className="stat-icon primary" />Estado</div>
          <div className="stat-value primary-text">{stats.activo ? 'Convirtiendo' : 'Inactivo'}</div>
        </div>
      </div>

      <div className="main-content">
        <div className="left-panel">
          <div className="glass-card table-card">
            <div className="tabs">
              <button className={`tab-btn ${activeTab === 'procesados' ? 'active' : ''}`} onClick={() => setActiveTab('procesados')}>
                PDFs Generados ({stats.procesados})
              </button>
              <button className={`tab-btn ${activeTab === 'pendientes' ? 'active' : ''}`} onClick={() => setActiveTab('pendientes')}>
                Imágenes ({stats.pendientes})
              </button>
              <button className={`tab-btn ${activeTab === 'erroneos' ? 'active' : ''}`} onClick={() => setActiveTab('erroneos')}>
                Erróneos ({stats.erroneos})
              </button>
            </div>

            {activeTab === 'procesados' && (
              <div>
                <div className="search-wrapper">
                  <Search size={16} color="var(--text-light)" />
                  <input
                    type="text"
                    placeholder="Buscar por nombre..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                </div>
                <div className="table-wrapper">
                  <table>
                    <thead>
                      <tr>
                        <th>Formato</th>
                        <th>Nombre</th>
                        <th>Tamaño</th>
                        <th>Fecha</th>
                        <th>Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredProcessed.length === 0 ? (
                        <tr><td colSpan="5" className="empty-state">No hay PDFs generados.</td></tr>
                      ) : (
                        filteredProcessed.map((doc, idx) => (
                          <tr key={`${doc.nombre}-${idx}`}>
                            <td><span className="badge pdf">PDF</span></td>
                            <td className="doc-name">{doc.nombre || 'N/A'}</td>
                            <td className="doc-meta">{doc.tamaño || '-'}</td>
                            <td className="doc-meta">{doc.fecha || '-'}</td>
                            <td>
                              <div className="actions">
                                <button className="btn-icon pdf" title="Descargar PDF" onClick={() => handleDownload(doc.nombre)}>
                                  <Download size={14} />
                                </button>
                                <button className="btn-icon folder" title="Abrir Carpeta" onClick={() => handleOpenFolder(doc.nombre)}>
                                  <Folder size={14} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {activeTab === 'pendientes' && (
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Nombre de Archivo</th>
                      <th>Tamaño</th>
                      <th>Formato</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingDocs.length === 0 ? (
                      <tr><td colSpan="3" className="empty-state">No hay imágenes pendientes.</td></tr>
                    ) : (
                      pendingDocs.map((doc, idx) => (
                        <tr key={`pending-${idx}`}>
                          <td className="doc-name">{doc.nombre || 'Desconocido'}</td>
                          <td className="doc-meta">{doc.tamaño || '-'}</td>
                          <td><span className="badge image">Imagen</span></td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {activeTab === 'erroneos' && (
              <div>
                {errorDocs.length > 0 && (
                  <div className="error-actions">
                    <button className="btn btn-primary" onClick={handleRetryAllErrors}>
                      <RotateCcw size={14} /> Reintentar Todos
                    </button>
                  </div>
                )}
                <div className="table-wrapper">
                  <table>
                    <thead>
                      <tr>
                        <th>Nombre</th>
                        <th>Error</th>
                        <th>Fecha</th>
                        <th>Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredErrors.length === 0 ? (
                        <tr><td colSpan="4" className="empty-state">No hay documentos con errores.</td></tr>
                      ) : (
                        filteredErrors.map((error, idx) => (
                          <tr key={`error-${idx}`}>
                            <td className="doc-name">{error.nombre || 'Desconocido'}</td>
                            <td className="error-message">{error.error}</td>
                            <td className="doc-meta">{error.fecha || '-'}</td>
                            <td>
                              <div className="actions">
                                <button className="btn-icon retry" title="Reintentar" onClick={() => handleRetryError(error.nombre)}>
                                  <RotateCcw size={14} />
                                </button>
                                <button className="btn-icon delete" title="Eliminar" onClick={() => handleDeleteError(error.nombre)}>
                                  <Trash2 size={14} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="right-panel">
          <div className="glass-card controls-card">
            <h3 className="section-title">Controles</h3>

            <div className="upload-zone">
              <UploadCloud size={28} className="upload-icon" />
              <div className="upload-title">Subir Imágenes</div>
              <p>Arrastra o selecciona archivos de imagen</p>
              <p className="upload-formats">Formatos: JPG, PNG, GIF, BMP, TIFF, WEBP</p>
              <input 
                type="file" 
                accept=".jpg,.jpeg,.png,.gif,.bmp,.tiff,.tif,.webp" 
                multiple 
                onChange={handleUpload} 
              />
            </div>

            <button
              className="btn btn-success btn-block"
              onClick={handleProcess}
              disabled={isProcessing || stats.activo}
            >
              {(isProcessing || stats.activo) ? <RefreshCw size={18} className="spinner" /> : <Image size={18} />}
              <span>{stats.activo ? 'Convirtiendo...' : 'Convertir a PDF Ahora'}</span>
            </button>

            <button
              className="btn btn-danger btn-block"
              onClick={handleStop}
              disabled={!stats.activo}
            >
              <Square size={18} />
              <span>Detener Proceso</span>
            </button>
            
            {!stats.activo && (
              <p className="auto-info">
                Conversión automática cada {stats.intervalo} minutos
              </p>
            )}
          </div>

          <div className="glass-card logs-card">
            <h3 className="section-title">
              <span>Log del Sistema</span>
              <div className="log-actions">
                <button className="btn-icon" title="Descargar Logs" onClick={handleDownloadLogs}>
                  <FileDown size={14} />
                </button>
                <button className="btn-icon" title="Limpiar Logs" onClick={handleClearLogs}>
                  <Trash2 size={14} />
                </button>
                <button className="btn-icon" title="Refrescar" onClick={fetchData}>
                  <RefreshCw size={14} />
                </button>
              </div>
            </h3>
            <div className="log-viewer">
              {logs.length === 0 ? (
                <div className="log-empty">Esperando logs...</div>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="log-line">{log}</div>
                ))
              )}
              <div ref={logEndRef} />
            </div>
          </div>
        </div>
      </div>

      {modal.show && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <div className="modal-title">
                {modal.type === 'warning' ? <AlertTriangle size={20} /> : <Info size={20} />}
                <h3>{modal.title}</h3>
              </div>
              <button className="btn-icon" onClick={closeModal}>
                <X size={18} />
              </button>
            </div>
            <div className="modal-body">
              <p>{modal.message}</p>
            </div>
            <div className="modal-footer">
              {modal.onConfirm ? (
                <>
                  <button className="btn btn-secondary" onClick={closeModal}>Cancelar</button>
                  <button className="btn btn-primary" onClick={() => { modal.onConfirm(); closeModal(); }}>Confirmar</button>
                </>
              ) : (
                <button className="btn btn-primary" onClick={closeModal}>Entendido</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;