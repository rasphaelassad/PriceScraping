
const container = document.getElementById('root');
const root = ReactDOM.createRoot(container);

// Wait for App to be defined
window.addEventListener('load', () => {
  root.render(
    React.createElement(React.StrictMode, null,
      React.createElement(window.App)
    )
  );
});
