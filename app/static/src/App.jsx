
import React, { useState } from 'react';
import { Container, Typography, Box, Button, TextField, IconButton, MenuItem, Select, Paper, Grid } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';

const SUPPORTED_STORES = ['walmart', 'chefstore', 'albertsons', 'costco'];

function App() {
  const [products, setProducts] = useState([]);
  const [newProductName, setNewProductName] = useState('');
  const [selectedProduct, setSelectedProduct] = useState('');
  const [selectedStore, setSelectedStore] = useState('');
  const [newProductUrl, setNewProductUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState({});

  const addProduct = () => {
    if (newProductName) {
      setProducts([...products, { id: Date.now(), name: newProductName, urls: {} }]);
      setNewProductName('');
    }
  };

  const addUrlToStore = () => {
    if (selectedProduct && selectedStore && newProductUrl) {
      setProducts(products.map(p => {
        if (p.id === parseInt(selectedProduct)) {
          return {
            ...p,
            urls: { ...p.urls, [selectedStore]: newProductUrl }
          };
        }
        return p;
      }));
      setNewProductUrl('');
      setSelectedStore('');
    }
  };

  const removeProduct = (id) => {
    setProducts(products.filter(p => p.id !== id));
    setResults(prevResults => {
      const newResults = { ...prevResults };
      delete newResults[id];
      return newResults;
    });
  };

  const scrapeAll = async () => {
    setLoading(true);
    const newResults = {};

    for (const store of SUPPORTED_STORES) {
      const urls = products
        .filter(p => p.urls[store])
        .map(p => ({
          productId: p.id,
          url: p.urls[store]
        }));

      if (urls.length > 0) {
        try {
          const response = await fetch('http://0.0.0.0:3000/api/get-prices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              store_name: store,
              urls: urls.map(u => u.url)
            })
          });
          const data = await response.json();
          
          urls.forEach(({ productId, url }) => {
            if (!newResults[productId]) {
              newResults[productId] = {};
            }
            newResults[productId][store] = data.results[url];
          });
        } catch (error) {
          console.error(`Error scraping ${store}:`, error);
        }
      }
    }

    setResults(newResults);
    setLoading(false);
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" gutterBottom>
        Price Comparison Tool
      </Typography>

      <Paper elevation={3} sx={{ p: 3, mb: 4 }}>
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Typography variant="h6" gutterBottom>
              Add New Product
            </Typography>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <TextField
                label="Product Name"
                value={newProductName}
                onChange={(e) => setNewProductName(e.target.value)}
                fullWidth
              />
              <Button variant="contained" onClick={addProduct}>
                Add Product
              </Button>
            </Box>
          </Grid>

          <Grid item xs={12}>
            <Typography variant="h6" gutterBottom>
              Add Store URL
            </Typography>
            <Box sx={{ display: 'flex', gap: 2 }}>
              <Select
                value={selectedProduct}
                onChange={(e) => setSelectedProduct(e.target.value)}
                displayEmpty
                fullWidth
              >
                <MenuItem value="" disabled>Select Product</MenuItem>
                {products.map((product) => (
                  <MenuItem key={product.id} value={product.id}>{product.name}</MenuItem>
                ))}
              </Select>
              <Select
                value={selectedStore}
                onChange={(e) => setSelectedStore(e.target.value)}
                displayEmpty
                fullWidth
              >
                <MenuItem value="" disabled>Select Store</MenuItem>
                {SUPPORTED_STORES.map((store) => (
                  <MenuItem key={store} value={store}>
                    {store.charAt(0).toUpperCase() + store.slice(1)}
                  </MenuItem>
                ))}
              </Select>
              <TextField
                label="Store URL"
                value={newProductUrl}
                onChange={(e) => setNewProductUrl(e.target.value)}
                fullWidth
              />
              <Button variant="contained" onClick={addUrlToStore}>
                Add URL
              </Button>
            </Box>
          </Grid>
        </Grid>
      </Paper>

      {products.map((product) => (
        <Paper key={product.id} elevation={2} sx={{ mb: 3, p: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>{product.name}</Typography>
            <IconButton onClick={() => removeProduct(product.id)} color="error">
              <DeleteIcon />
            </IconButton>
          </Box>

          <Grid container spacing={2}>
            {SUPPORTED_STORES.map((store) => (
              <Grid item xs={12} sm={6} key={store}>
                <Typography variant="subtitle2">
                  {store.charAt(0).toUpperCase() + store.slice(1)}:
                </Typography>
                <Typography variant="body2" sx={{ wordBreak: 'break-all' }}>
                  {product.urls[store] || 'No URL added'}
                </Typography>
                {results[product.id]?.hasOwnProperty(store) && (
                  <Typography color="primary">
                    Price: ${results[product.id][store]?.result?.price || 'N/A'}
                  </Typography>
                )}
              </Grid>
            ))}
          </Grid>
        </Paper>
      ))}

      <Box sx={{ mt: 4 }}>
        <Button
          variant="contained"
          onClick={scrapeAll}
          disabled={loading}
          size="large"
          fullWidth
        >
          {loading ? 'Scraping...' : 'Scrape All Prices'}
        </Button>
      </Box>
    </Container>
  );
}

export default App;
