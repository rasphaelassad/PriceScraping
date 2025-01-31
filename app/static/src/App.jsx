
const { useState } = React;
const { Container, Typography, Box, Button, TextField, Paper, Grid, Select, MenuItem, FormControl, InputLabel } = MaterialUI;

function App() {
  const [urls, setUrls] = useState([]);
  const [currentUrl, setCurrentUrl] = useState('');
  const [selectedStore, setSelectedStore] = useState('walmart');
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleAddUrl = () => {
    if (currentUrl && !urls.includes(currentUrl)) {
      setUrls([...urls, currentUrl]);
      setCurrentUrl('');
    }
  };

  const handleRemoveUrl = (urlToRemove) => {
    setUrls(urls.filter(url => url !== urlToRemove));
  };

  const handleSubmit = async () => {
    if (urls.length === 0) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/get-prices', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          store_name: selectedStore,
          urls: urls
        }),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Failed to fetch prices');
      setResults(data.results);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container>
      <Typography variant="h4" component="h1" gutterBottom>
        Price Comparison Tool
      </Typography>
      
      <Paper elevation={3} sx={{ p: 2, mb: 2 }}>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth>
              <InputLabel>Store</InputLabel>
              <Select
                value={selectedStore}
                onChange={(e) => setSelectedStore(e.target.value)}
                label="Store"
              >
                <MenuItem value="walmart">Walmart</MenuItem>
                <MenuItem value="albertsons">Albertsons</MenuItem>
                <MenuItem value="costco">Costco</MenuItem>
                <MenuItem value="chefstore">Chef Store</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12}>
            <TextField
              fullWidth
              label="Product URL"
              value={currentUrl}
              onChange={(e) => setCurrentUrl(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleAddUrl()}
            />
          </Grid>
          <Grid item xs={12}>
            <Button variant="contained" onClick={handleAddUrl}>
              Add URL
            </Button>
          </Grid>
        </Grid>

        {urls.length > 0 && (
          <Box mt={2}>
            <Typography variant="h6">Added URLs:</Typography>
            {urls.map((url, index) => (
              <Box key={index} display="flex" alignItems="center" mt={1}>
                <Typography noWrap style={{ flex: 1 }}>{url}</Typography>
                <Button onClick={() => handleRemoveUrl(url)} color="error">
                  Remove
                </Button>
              </Box>
            ))}
            <Button
              variant="contained"
              color="primary"
              onClick={handleSubmit}
              disabled={loading}
              sx={{ mt: 2 }}
            >
              {loading ? 'Loading...' : 'Get Prices'}
            </Button>
          </Box>
        )}
      </Paper>

      {error && (
        <Paper elevation={3} sx={{ p: 2, mb: 2, bgcolor: '#ffebee' }}>
          <Typography color="error">{error}</Typography>
        </Paper>
      )}

      {results && (
        <Paper elevation={3} sx={{ p: 2 }}>
          <Typography variant="h6">Results:</Typography>
          {Object.entries(results).map(([url, data]) => (
            <Box key={url} mt={2}>
              <Typography variant="subtitle1">
                Product: {data.result?.name || 'N/A'}
              </Typography>
              <Typography>
                Price: {data.result?.price_string || 'N/A'}
              </Typography>
              <Typography>
                Price per unit: {data.result?.price_per_unit_string || 'N/A'}
              </Typography>
            </Box>
          ))}
        </Paper>
      )}
    </Container>
  );
}

window.App = App;
