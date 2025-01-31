
const container = document.getElementById('root');
const root = ReactDOM.createRoot(container);

root.render(
  React.createElement(React.StrictMode, null,
    React.createElement(window.App)
  )
);
