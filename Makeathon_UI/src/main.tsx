import React from "react"
import ReactDOM from "react-dom/client"
import App from "./LiveApp"
import "./index.css"
import { installDetailsAnimation, trackStickyTitles } from "./details-animation"

installDetailsAnimation()
trackStickyTitles()

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
