import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'
import App from './App.jsx'
import { StoreProvider } from './store.js'
import { UiProvider } from './ui.jsx'
import { ThemeProvider } from './theme.jsx'
import { ToastProvider } from './components/ui/index.js'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <StoreProvider>
          <UiProvider>
            <App />
          </UiProvider>
        </StoreProvider>
      </ToastProvider>
    </ThemeProvider>
  </React.StrictMode>,
)
