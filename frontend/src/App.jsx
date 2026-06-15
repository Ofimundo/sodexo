import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Activity, FileText, CheckCircle, UploadCloud, Play, RefreshCw, Server, Search, Folder, Square, Settings, Save, Edit3, Trash2, FileDown, AlertTriangle, Info, X, AlertCircle, RotateCcw, Briefcase, Shield, Receipt, DollarSign, Database, Eye } from 'lucide-react';
import logoOfilab from './assets/logo_ofilab.png';
import './index.css';

const API_URL = window.location.origin === 'http://localhost:5173' ? 'http://localhost:5000/api' : '/api';

// Tipos de documentos soportados
const DOCUMENT_TYPES = {
  LABORAL: {
    id: 'laboral',
    name: 'Laboral',
    icon: 'Briefcase',
    subTypes: ['vacaciones', 'permisos', 'amonestaciones', 'contratos'],
    fields: {
      empleado_nombre: 'Nombre del empleado',
      empleado_rut: 'RUT del empleado',
      fecha_documento: 'Fecha del documento',
      tipo_licencia: 'Tipo de licencia/permiso',
      fecha_inicio: 'Fecha inicio',
      fecha_termino: 'Fecha término',
      motivo: 'Motivo',
      empleador: 'Nombre del empleador',
      cargo: 'Cargo del empleado',
      sueldo_base: 'Sueldo base',
      duracion_dias: 'Duración en días'
    }
  },
  SEGURIDAD_LABORAL: {
    id: 'seguridad',
    name: 'Seguridad Laboral',
    icon: 'Shield',
    subTypes: ['medidas_prevencion', 'ordenes_trabajo', 'capacitaciones', 'accidentes'],
    fields: {
      folio_documento: 'Folio del documento',
      fecha_emision: 'Fecha de emisión',
      area_trabajo: 'Área de trabajo',
      tipo_medida: 'Tipo de medida',
      descripcion: 'Descripción',
      responsable: 'Responsable',
      fecha_ejecucion: 'Fecha de ejecución',
      estado: 'Estado',
      observaciones: 'Observaciones'
    }
  },
  FACTURACION: {
    id: 'facturacion',
    name: 'Facturación',
    icon: 'Receipt',
    subTypes: ['factura', 'orden_compra', 'boleta', 'nota_credito'],
    fields: {
      folio: 'Folio/Número',
      rut_emisor: 'RUT Emisor',
      razon_social_emisor: 'Razón Social Emisor',
      rut_receptor: 'RUT Receptor',
      razon_social_receptor: 'Razón Social Receptor',
      fecha_emision: 'Fecha Emisión',
      monto_total: 'Monto Total',
      neto: 'Neto',
      iva: 'IVA',
      tipo_dte: 'Tipo DTE',
      numero_dte: 'Número DTE'
    }
  },
  FINANCIERO: {
    id: 'financiero',
    name: 'Financiero',
    icon: 'DollarSign',
    subTypes: ['libro_contabilidad', 'balance', 'estado_resultados', 'inventario'],
    fields: {
      periodo: 'Período contable',
      fecha_corte: 'Fecha de corte',
      tipo_libro: 'Tipo de libro',
      cuenta_contable: 'Cuenta contable',
      saldo_inicial: 'Saldo inicial',
      debe: 'Debe',
      haber: 'Haber',
      saldo_final: 'Saldo final',
      moneda: 'Moneda',
      glosa: 'Glosa'
    }
  }
};

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
  const destinationFolderRef = useRef(null);
  const isFetchingRef = useRef(false);

  const [stats, setStats] = useState({ pendientes: 0, procesados: 0, erroneos: 0, activo: false, intervalo: 5 });
  const [pendingDocs, setPendingDocs] = useState([]);
  const [processedDocs, setProcessedDocs] = useState([]);
  const [errorDocs, setErrorDocs] = useState([]);
  const [logs, setLogs] = useState([]);
  const [activeTab, setActiveTab] = useState('procesados');
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [isProcessing, setIsProcessing] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [selectedDocDetail, setSelectedDocDetail] = useState(null);
  const [config, setConfig] = useState({
    ruta_pendientes: '',
    ruta_procesados: '',
    ruta_destino: '',
    intervalo: 5,
    persistente: false,
    calidad_ocr: 'alta',
    formato_salida: 'pdf'
  });
  const [guardarPermanente, setGuardarPermanente] = useState(true);
  const [modal, setModal] = useState({ show: false, title: '', message: '', type: 'info', onConfirm: null });
  const [backendOff, setBackendOff] = useState(false);
  const logEndRef = useRef(null);

  const fetchData = useCallback(async () => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;

    try {
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

      const pendingData = await safeFetch(`${API_URL}/pending`);
      if (Array.isArray(pendingData)) {
        setPendingDocs(pendingData.filter(d => d && typeof d === 'object').map(d => ({
          nombre: String(d.nombre || ''),
          tamaño: String(d.tamaño || ''),
          fecha: String(d.fecha || ''),
          tipo_sugerido: d.tipo_sugerido || 'desconocido'
        })));
      }

      const processedData = await safeFetch(`${API_URL}/processed`);
      if (Array.isArray(processedData)) {
        setProcessedDocs(processedData.filter(d => d && typeof d === 'object').map(d => ({
          id: String(d.id || ''),
          tipo: String(d.tipo || 'desconocido'),
          subtipo: String(d.subtipo || ''),
          folio: String(d.folio || ''),
          rut: String(d.rut || ''),
          fecha: String(d.fecha || ''),
          archivos: Array.isArray(d.archivos) ? d.archivos.map(String) : [],
          metadata: d.metadata || {},
          preview_url: d.preview_url || '',
          calidad_imagen: d.calidad_imagen || 'alta'
        })));
      }

      const errorData = await safeFetch(`${API_URL}/errors`);
      if (Array.isArray(errorData)) {
        setErrorDocs(errorData.filter(e => e && typeof e === 'object').map(e => ({
          nombre: String(e.nombre || ''),
          error: String(e.error || 'Error desconocido'),
          fecha: String(e.fecha || ''),
          tamaño: String(e.tamaño || '')
        })));
      }

      const logsData = await safeFetch(`${API_URL}/logs`);
      if (logsData && Array.isArray(logsData.logs)) {
        setLogs(logsData.logs.map(String));
      }

      if (!showConfig) {
        const cfgData = await safeFetch(`${API_URL}/config`);
        if (cfgData && typeof cfgData === 'object' && !cfgData.error) {
          setConfig(prev => ({
            ...prev,
            ruta_pendientes: String(cfgData.ruta_pendientes || ''),
            ruta_procesados: String(cfgData.ruta_procesados || ''),
            ruta_destino: String(cfgData.ruta_destino || ''),
            intervalo: Number(cfgData.intervalo) || 5,
            persistente: !!cfgData.persistente,
            calidad_ocr: cfgData.calidad_ocr || 'alta',
            formato_salida: cfgData.formato_salida || 'pdf'
          }));
          setGuardarPermanente(!!cfgData.persistente);
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

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    const validExtensions = ['.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'];
    const fileExt = '.' + file.name.split('.').pop().toLowerCase();
    if (!validExtensions.includes(fileExt)) {
      setModal({
        show: true,
        title: 'Formato no soportado',
        message: `El formato ${fileExt} no está soportado. Formatos permitidos: PDF, PNG, JPG, JPEG, TIFF, BMP`,
        type: 'warning'
      });
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('calidad', config.calidad_ocr);
    await safeFetch(`${API_URL}/upload`, { method: 'POST', body: formData });
    fetchData();
  };

  const handleProcess = async () => {
    try {
      setIsProcessing(true);
      await safeFetch(`${API_URL}/process`, { method: 'POST', body: JSON.stringify({ calidad: config.calidad_ocr }), headers: { 'Content-Type': 'application/json' } });
    } finally {
      setTimeout(() => setIsProcessing(false), 2000);
    }
  };

  const handleViewDocument = async (docId) => {
    const doc = processedDocs.find(d => d.id === docId);
    if (doc) {
      setSelectedDocDetail(doc);
    }
  };

  const handleRetryError = async (fileName) => {
    setModal({
      show: true,
      title: 'Reintentar Documento',
      message: `¿Deseas reintentar el procesamiento del documento "${fileName}"?`,
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
      message: `¿Deseas reintentar el procesamiento de todos los documentos erróneos (${errorDocs.length})?`,
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
      message: `¿Estás seguro de que deseas eliminar el documento "${fileName}" de la lista de errores?`,
      type: 'warning',
      onConfirm: async () => {
        await safeFetch(`${API_URL}/delete-error/${encodeURIComponent(fileName)}`, { method: 'DELETE' });
        fetchData();
      }
    });
  };

  const handleDownload = (type, docId) => {
    window.open(`${API_URL}/download/${type}/${encodeURIComponent(docId)}`, '_blank');
  };

  const handleOpenFolder = async (docId) => {
    await safeFetch(`${API_URL}/open/${encodeURIComponent(docId)}`, { method: 'POST' });
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
      ruta_procesados: processedFolderRef,
      ruta_destino: destinationFolderRef
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
  const closeDetailModal = () => setSelectedDocDetail(null);

  const getIconForType = (typeId) => {
    const icons = {
      laboral: Briefcase,
      seguridad: Shield,
      facturacion: Receipt,
      financiero: DollarSign
    };
    const Icon = icons[typeId] || FileText;
    return <Icon size={18} />;
  };

  const filteredProcessed = processedDocs.filter(doc => {
    const term = searchTerm.toLowerCase();
    const matchesSearch = doc.folio.toLowerCase().includes(term) || 
                         doc.tipo.toLowerCase().includes(term) ||
                         (doc.metadata?.empleado_nombre || '').toLowerCase().includes(term);
    const matchesType = filterType === 'all' || doc.tipo === filterType;
    return matchesSearch && matchesType;
  });

  const filteredErrors = errorDocs.filter(error => {
    const term = searchTerm.toLowerCase();
    return error.nombre.toLowerCase().includes(term) || error.error.toLowerCase().includes(term);
  });

  const getBadgeClass = (tipo) => {
    const classes = {
      laboral: 'laboral',
      seguridad: 'seguridad',
      facturacion: 'facturacion',
      financiero: 'financiero'
    };
    return classes[tipo] || 'default';
  };

  return (
    <div className="app-container">
      <header>
        <div className="logo-container">
          <div className="logo-wrapper-glow logo-large">
            <img 
              src={logoOfilab} 
              alt="Ofilab Logo" 
              className="logo-img"
              onError={(e) => {
                e.target.style.display = 'none';
                e.target.parentElement.innerHTML = '<div class="logo-fallback-text">OFILAB</div>';
              }}
            />
          </div>
          <h1>
            <span>Sistema OCR Transversal - Digitalización Inteligente</span>
          </h1>
        </div>
        <div className="header-actions">
          {backendOff && (
            <span className="backend-warning">
              ⚠ Sin conexión al servidor
            </span>
          )}
          <button
            className="btn-config"
            title="Configuración"
            onClick={() => setShowConfig(v => !v)}
          >
            <Settings size={22} />
            <span className="config-text">Configuración</span>
          </button>
          <div className={`status-badge ${stats.activo ? 'active' : 'inactive'}`}>
            <div className="status-dot"></div>
            <span>{stats.activo ? 'Procesando' : 'En Espera'}</span>
            <span className="interval-text">(Auto: {stats.intervalo}m)</span>
          </div>
        </div>
      </header>

      {showConfig && (
        <div className="config-card">
          <h2 className="config-title">
            <Settings size={20} /> Configuración del Sistema
          </h2>
          <div className="config-grid">
            {[
              { label: 'Carpeta de Entrada (Pendientes)', key: 'ruta_pendientes' },
              { label: 'Carpeta Local (Procesados)', key: 'ruta_procesados' },
              { label: 'Carpeta de Salida (Destino Final)', key: 'ruta_destino' },
            ].map(({ label, key }) => (
              <div key={key}>
                <label className="config-label">{label}</label>
                <div className="config-input-group">
                  <input
                    className="config-input"
                    value={config[key]}
                    onChange={(e) => setConfig(prev => ({ ...prev, [key]: e.target.value }))}
                  />
                  <button className="btn-icon" onClick={() => handleBrowse(key)}><Folder size={16} /></button>
                </div>
              </div>
            ))}
            <div>
              <label className="config-label">Intervalo (Minutos)</label>
              <input
                type="number"
                className="config-input"
                value={config.intervalo}
                onChange={(e) => setConfig(prev => ({ ...prev, intervalo: e.target.value }))}
              />
            </div>
            <div>
              <label className="config-label">Calidad OCR</label>
              <select
                className="config-select"
                value={config.calidad_ocr}
                onChange={(e) => setConfig(prev => ({ ...prev, calidad_ocr: e.target.value }))}
              >
                <option value="alta">Alta (Mejor calidad, más espacio)</option>
                <option value="media">Media (Balance calidad/espacio)</option>
                <option value="baja">Baja (Menor calidad, menor espacio)</option>
              </select>
            </div>
            <div>
              <label className="config-label">Formato de Salida</label>
              <select
                className="config-select"
                value={config.formato_salida}
                onChange={(e) => setConfig(prev => ({ ...prev, formato_salida: e.target.value }))}
              >
                <option value="pdf">PDF (Recomendado)</option>
                <option value="pdf_a">PDF/A (Archivo a largo plazo)</option>
                <option value="jpg">JPG (Imagen comprimida)</option>
                <option value="png">PNG (Calidad sin pérdida)</option>
              </select>
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
            <button className="btn-secondary" onClick={() => setShowConfig(false)}>Cancelar</button>
            <button className="btn-primary" onClick={handleSaveConfig}><Save size={18} /> Guardar Cambios</button>
            <input type="file" webkitdirectory="true" multiple style={{ display: 'none' }} ref={pendingFolderRef} onChange={(e) => handleFolderSelect(e, 'ruta_pendientes')} />
            <input type="file" webkitdirectory="true" multiple style={{ display: 'none' }} ref={processedFolderRef} onChange={(e) => handleFolderSelect(e, 'ruta_procesados')} />
            <input type="file" webkitdirectory="true" multiple style={{ display: 'none' }} ref={destinationFolderRef} onChange={(e) => handleFolderSelect(e, 'ruta_destino')} />
          </div>
        </div>
      )}

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-title"><CheckCircle size={16} /> Procesados</div>
          <div className="stat-value success-text">{stats.procesados}</div>
        </div>
        <div className="stat-card">
          <div className="stat-title"><FileText size={16} /> Pendientes</div>
          <div className="stat-value danger-text">{stats.pendientes}</div>
        </div>
        <div className="stat-card">
          <div className="stat-title"><AlertCircle size={16} /> Erróneos</div>
          <div className="stat-value warning-text">{stats.erroneos}</div>
        </div>
        <div className="stat-card">
          <div className="stat-title"><Activity size={16} /> Estado del Sistema</div>
          <div className="stat-value primary-text">{stats.activo ? 'Ejecutando' : 'Inactivo'}</div>
        </div>
      </div>

      <div className="main-content">
        <div className="left-panel">
          <div className="content-card">
            <div className="tabs">
              <button className={`tab-btn ${activeTab === 'procesados' ? 'active' : ''}`} onClick={() => setActiveTab('procesados')}>
                Procesados ({stats.procesados})
              </button>
              <button className={`tab-btn ${activeTab === 'pendientes' ? 'active' : ''}`} onClick={() => setActiveTab('pendientes')}>
                Pendientes ({stats.pendientes})
              </button>
              <button className={`tab-btn ${activeTab === 'erroneos' ? 'active' : ''}`} onClick={() => setActiveTab('erroneos')}>
                Erróneos ({stats.erroneos})
              </button>
            </div>

            {activeTab === 'procesados' && (
              <div>
                <div className="search-bar">
                  <Search size={18} color="#7f8c8d" />
                  <input
                    type="text"
                    placeholder="Buscar por folio, tipo, nombre empleado..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                  />
                  <select
                    className="filter-select"
                    value={filterType}
                    onChange={(e) => setFilterType(e.target.value)}
                  >
                    <option value="all">Todos los tipos</option>
                    <option value="laboral">📄 Laboral</option>
                    <option value="seguridad">🛡️ Seguridad Laboral</option>
                    <option value="facturacion">🧾 Facturación</option>
                    <option value="financiero">💰 Financiero</option>
                  </select>
                </div>
                <div className="table-container">
                  <table className="documents-table">
                    <thead>
                      <tr>
                        <th>Tipo</th>
                        <th>Subtipo</th>
                        <th>Folio/ID</th>
                        <th>Información Relevante</th>
                        <th>Fecha</th>
                        <th>Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredProcessed.length === 0 ? (
                        <tr>
                          <td colSpan="6" className="empty-state">No hay documentos procesados.</td>
                        </tr>
                      ) : (
                        filteredProcessed.map((doc) => (
                          <tr key={doc.id}>
                            <td>
                              <span className={`badge ${getBadgeClass(doc.tipo)}`}>
                                {getIconForType(doc.tipo)} {DOCUMENT_TYPES[doc.tipo.toUpperCase()]?.name || doc.tipo}
                              </span>
                            </td>
                            <td className="subtipo-cell">{doc.subtipo || '-'}</td>
                            <td className="folio-cell">{doc.folio || 'N/A'}</td>
                            <td className="info-cell">
                              {doc.tipo === 'laboral' && doc.metadata?.empleado_nombre && (
                                <span>👤 {doc.metadata.empleado_nombre}</span>
                              )}
                              {doc.tipo === 'facturacion' && doc.metadata?.monto_total && (
                                <span>💰 ${parseInt(doc.metadata.monto_total).toLocaleString()}</span>
                              )}
                              {doc.tipo === 'seguridad' && doc.metadata?.area_trabajo && (
                                <span>🏭 {doc.metadata.area_trabajo}</span>
                              )}
                              {doc.tipo === 'financiero' && doc.metadata?.periodo && (
                                <span>📅 {doc.metadata.periodo}</span>
                              )}
                              {(!doc.metadata || Object.keys(doc.metadata).length === 0) && '-'}
                            </td>
                            <td className="date-cell">{doc.fecha || '-'}</td>
                            <td>
                              <div className="actions">
                                <button className="btn-icon view" title="Ver Detalles" onClick={() => handleViewDocument(doc.id)}>
                                  <Eye size={14} />
                                </button>
                                <button className="btn-icon pdf" title="Descargar" onClick={() => handleDownload('pdf', doc.id)}>PDF</button>
                                <button className="btn-icon xml" title="Descargar XML" onClick={() => handleDownload('xml', doc.id)}>XML</button>
                                <button className="btn-icon folder" title="Abrir Carpeta" onClick={() => handleOpenFolder(doc.id)}><Folder size={14} /></button>
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
              <div className="table-container">
                <table className="documents-table">
                  <thead>
                    <tr>
                      <th>Nombre de Archivo</th>
                      <th>Tamaño</th>
                      <th>Tipo Sugerido</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pendingDocs.length === 0 ? (
                      <tr>
                        <td colSpan="3" className="empty-state">No hay documentos pendientes.</td>
                      </tr>
                    ) : (
                      pendingDocs.map((doc, idx) => (
                        <tr key={`pending-${idx}`}>
                          <td className="filename-cell">{doc.nombre || 'Desconocido'}</td>
                          <td className="size-cell">{doc.tamaño || '-'}</td>
                          <td>
                            <span className={`badge ${getBadgeClass(doc.tipo_sugerido)}`}>
                              {DOCUMENT_TYPES[doc.tipo_sugerido?.toUpperCase()]?.name || 'Auto-detectar'}
                            </span>
                          </td>
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
                  <div className="retry-all-container">
                    <button className="btn-primary-small" onClick={handleRetryAllErrors}>
                      <RotateCcw size={16} /> Reintentar Todos
                    </button>
                  </div>
                )}
                <div className="table-container">
                  <table className="documents-table">
                    <thead>
                      <tr>
                        <th>Nombre de Archivo</th>
                        <th>Error</th>
                        <th>Fecha</th>
                        <th>Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredErrors.length === 0 ? (
                        <tr>
                          <td colSpan="4" className="empty-state">No hay documentos con errores.</td>
                        </tr>
                      ) : (
                        filteredErrors.map((error, idx) => (
                          <tr key={`error-${idx}`}>
                            <td className="filename-cell">{error.nombre || 'Desconocido'}</td>
                            <td className="error-cell">{error.error}</td>
                            <td className="date-cell">{error.fecha || '-'}</td>
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
          <div className="controls-card">
            <h3>Controles de Digitalización</h3>

            <div className="file-input-wrapper">
              <button className="btn-primary-full">
                <UploadCloud size={20} />
                <span>Subir Documento</span>
              </button>
              <input type="file" accept=".pdf,.png,.jpg,.jpeg,.tiff,.bmp" onChange={handleUpload} />
            </div>

            <button
              className="btn-success-full"
              onClick={handleProcess}
              disabled={isProcessing || stats.activo}
            >
              {(isProcessing || stats.activo) ? <RefreshCw size={20} className="spinner" /> : <Play size={20} />}
              <span>{stats.activo ? 'Digitalizando...' : 'Ejecutar Digitalización Ahora'}</span>
            </button>

            <button
              className="btn-danger-full"
              onClick={handleStop}
              disabled={!stats.activo}
            >
              <Square size={20} />
              <span>Detener Proceso</span>
            </button>
            
            {!stats.activo && (
              <p className="info-text">
                Digitalización automática cada {stats.intervalo} min | Calidad: {config.calidad_ocr === 'alta' ? 'Alta' : config.calidad_ocr === 'media' ? 'Media' : 'Baja'}
              </p>
            )}
          </div>

          <div className="logs-card">
            <h3 className="logs-header">
              Log del Sistema
              <div className="logs-actions">
                <button className="btn-icon-small" title="Descargar Logs" onClick={handleDownloadLogs}>
                  <FileDown size={14} />
                </button>
                <button className="btn-icon-small" title="Limpiar Logs" onClick={handleClearLogs}>
                  <Trash2 size={14} />
                </button>
                <button className="btn-icon-small" title="Refrescar" onClick={fetchData}>
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

      {/* Modal de detalle del documento */}
      {selectedDocDetail && (
        <div className="modal-overlay" onClick={closeDetailModal}>
          <div className="modal-content-detail" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                {getIconForType(selectedDocDetail.tipo)}
                <h3>Detalles del Documento</h3>
              </div>
              <button className="close-btn" onClick={closeDetailModal}><X size={18} /></button>
            </div>
            <div className="modal-body">
              <div className="doc-info">
                <p><strong>Tipo:</strong> {DOCUMENT_TYPES[selectedDocDetail.tipo?.toUpperCase()]?.name || selectedDocDetail.tipo}</p>
                <p><strong>Subtipo:</strong> {selectedDocDetail.subtipo || 'No especificado'}</p>
                <p><strong>Folio/ID:</strong> {selectedDocDetail.folio || 'N/A'}</p>
                <p><strong>Fecha:</strong> {selectedDocDetail.fecha || 'No disponible'}</p>
                <p><strong>Calidad de imagen:</strong> 
                  <span className={`quality-badge ${selectedDocDetail.calidad_imagen}`}>
                    {selectedDocDetail.calidad_imagen === 'alta' ? 'Alta' : selectedDocDetail.calidad_imagen === 'media' ? 'Media' : 'Baja'}
                  </span>
                </p>
              </div>
              
              <h4>Datos Extraídos por OCR:</h4>
              {selectedDocDetail.metadata && Object.keys(selectedDocDetail.metadata).length > 0 ? (
                <div className="metadata-grid">
                  {Object.entries(selectedDocDetail.metadata).map(([key, value]) => (
                    <div key={key} className="metadata-item">
                      <strong>{key.replace(/_/g, ' ').toUpperCase()}:</strong>
                      <span>{value || '-'}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="no-data">No se pudieron extraer datos estructurados de este documento.</p>
              )}
              
              {selectedDocDetail.preview_url && (
                <div className="preview-container">
                  <h4>Vista previa:</h4>
                  <iframe src={selectedDocDetail.preview_url} title="Vista previa" />
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn-primary-modal" onClick={closeDetailModal}>Cerrar</button>
            </div>
          </div>
        </div>
      )}

      {modal.show && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <div className="modal-title">
                {modal.type === 'warning' ? <AlertTriangle color="#D2446A" /> : <Info color="#70317A" />}
                <h3>{modal.title}</h3>
              </div>
              <button className="close-btn" onClick={closeModal}><X size={18} /></button>
            </div>
            <div className="modal-body">
              <p>{modal.message}</p>
            </div>
            <div className="modal-footer">
              {modal.onConfirm ? (
                <>
                  <button className="btn-secondary-modal" onClick={closeModal}>Cancelar</button>
                  <button className="btn-primary-modal" onClick={() => { modal.onConfirm(); closeModal(); }}>Confirmar</button>
                </>
              ) : (
                <button className="btn-primary-modal" onClick={closeModal}>Entendido</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;