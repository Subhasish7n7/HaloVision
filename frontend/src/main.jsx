import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { TTSProvider } from './context/TTSContext'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <TTSProvider>
        <App />
      </TTSProvider>
    </BrowserRouter>
  </React.StrictMode>
)
