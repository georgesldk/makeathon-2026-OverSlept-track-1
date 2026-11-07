import React from "react"
import ReactDOM from "react-dom/client"
import App from "./LiveApp"
import "./index.css"
import { installDetailsAnimation } from "./details-animation"
import { applyDisplay } from "./accessibility"

applyDisplay()
installDetailsAnimation()

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
