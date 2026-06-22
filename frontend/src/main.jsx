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
    console.error('Error en la aplicación:', error, errorInfo);
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
          background: '#f8f9fc',
          color: '#1a1a2e',
          fontFamily: 'Inter, sans-serif',
          padding: '2rem',
          textAlign: 'center',
          gap: '1.5rem'
        }}>
          <div style={{ fontSize: '4rem' }}>⚠️</div>
          <h2 style={{ fontSize: '1.5rem', background: 'linear-gradient(135deg, #2E2096, #E3314F)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Ocurrió un error en la interfaz
          </h2>
          <p style={{ color: '#6b7280', maxWidth: '500px' }}>
            La aplicación tuvo un problema al renderizar. Haz clic en el botón para recuperar sin recargar la página.
          </p>
          <pre style={{
            background: 'white',
            padding: '1rem',
            borderRadius: '0.75rem',
            fontSize: '0.75rem',
            color: '#E3314F',
            maxWidth: '600px',
            overflowX: 'auto',
            textAlign: 'left',
            border: '1px solid rgba(46, 32, 150, 0.1)',
            boxShadow: '0 2px 8px rgba(46, 32, 150, 0.06)'
          }}>
            {this.state.error?.message || 'Error desconocido'}
          </pre>
          <button
            onClick={this.handleRecover}
            style={{
              background: 'linear-gradient(135deg, #2E2096, #E3314F)',
              color: 'white',
              border: 'none',
              padding: '0.75rem 2rem',
              borderRadius: '0.75rem',
              fontSize: '1rem',
              cursor: 'pointer',
              fontWeight: '600',
              boxShadow: '0 4px 16px rgba(46, 32, 150, 0.25)'
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
