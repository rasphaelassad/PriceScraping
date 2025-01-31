
const { useState } = React;
const { Container, Typography, Box, Button, TextField, Paper, Grid } = MaterialUI;

function App() {
  const [value, setValue] = useState('');

  return (
    <Container>
      <Typography variant="h4" component="h1" gutterBottom>
        Price Comparison Tool
      </Typography>
      <Paper elevation={3} sx={{ p: 2, mt: 2 }}>
        <Typography>Welcome! Start by adding product URLs to compare prices.</Typography>
      </Paper>
    </Container>
  );
}

// Export the App component
window.App = App;
