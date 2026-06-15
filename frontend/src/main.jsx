import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Error Boundary: atrapa cualquier crash en React y muestra un mensaje en vez de pantalla en blanco
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Error en la aplicación OCR:', error, errorInfo);
  }

  handleRecover = () => {
    this.setState({ hasError: false, error: null });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          background: '#0f172a',
          color: '#f8fafc',
          fontFamily: 'Inter, sans-serif',
          padding: '2rem',
          textAlign: 'center',
          gap: '1.5rem'
        }}>
          <div style={{ fontSize: '4rem' }}>⚠️</div>
          <h2 style={{ fontSize: '1.5rem', color: '#ef4444' }}>
            Ocurrió un error en la interfaz
          </h2>
          <p style={{ color: '#94a3b8', maxWidth: '500px' }}>
            La aplicación tuvo un problema al renderizar. Esto puede ocurrir durante el procesamiento.
            Haz clic en el botón para recuperar sin recargar la página.
          </p>
          <pre style={{
            background: '#1e293b',
            padding: '1rem',
            borderRadius: '0.5rem',
            fontSize: '0.75rem',
            color: '#f59e0b',
            maxWidth: '600px',
            overflowX: 'auto',
            textAlign: 'left'
          }}>
            {this.state.error?.message || 'Error desconocido'}
          </pre>
          <button
            onClick={this.handleRecover}
            style={{
              background: '#3b82f6',
              color: 'white',
              border: 'none',
              padding: '0.75rem 2rem',
              borderRadius: '0.5rem',
              fontSize: '1rem',
              cursor: 'pointer',
              fontWeight: '600'
            }}
          >
            🔄 Recuperar aplicación
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

createRoot(document.getElementById('root')).render(
  // Sin StrictMode para evitar doble ejecución de efectos en desarrollo
  <ErrorBoundary>
    <App />
  </ErrorBoundary>
)
