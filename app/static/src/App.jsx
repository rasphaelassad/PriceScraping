
import React, { useState } from 'react';
import { Container, Typography, Box, Button, TextField, IconButton } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';

const SUPPORTED_STORES = ['walmart', 'chefstore', 'albertsons', 'costco'];

function App() {
  const [products, setProducts] = useState([
    { id: 1, name: '', urls: {} }
  ]);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState({});

  const addProduct = () => {
    setProducts([...products, { 
      id: Date.now(), 
      name: '', 
      urls: {}
    }]);
  };

  const removeProduct = (id) => {
    setProducts(products.filter(p => p.id !== id));
  };

  const updateProduct = (id, field, value) => {
    setProducts(products.map(p => {
      if (p.id === id) {
        return { ...p, [field]: value };
      }
      return p;
    }));
  };

  const updateUrl = (productId, store, url) => {
    setProducts(products.map(p => {
      if (p.id === productId) {
        return { 
          ...p, 
          urls: { ...p.urls, [store]: url }
        };
      }
      return p;
    }));
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
          const response = await fetch('http://localhost:8000/get-prices', {
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

      {products.map((product) => (
        <Box key={product.id} sx={{ mb: 4, p: 2, border: '1px solid #ddd', borderRadius: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
            <TextField
              label="Product Name"
              value={product.name}
              onChange={(e) => updateProduct(product.id, 'name', e.target.value)}
              sx={{ flexGrow: 1, mr: 2 }}
            />
            <IconButton onClick={() => removeProduct(product.id)} color="error">
              <DeleteIcon />
            </IconButton>
          </Box>

          {SUPPORTED_STORES.map((store) => (
            <TextField
              key={store}
              label={`${store.charAt(0).toUpperCase() + store.slice(1)} URL`}
              value={product.urls[store] || ''}
              onChange={(e) => updateUrl(product.id, store, e.target.value)}
              fullWidth
              sx={{ mb: 1 }}
            />
          ))}

          {results[product.id] && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="h6">Results:</Typography>
              {Object.entries(results[product.id]).map(([store, result]) => (
                <Box key={store} sx={{ ml: 2 }}>
                  <Typography>
                    {store}: ${result?.result?.price || 'N/A'}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}
        </Box>
      ))}

      <Box sx={{ mt: 2 }}>
        <Button variant="outlined" onClick={addProduct} sx={{ mr: 2 }}>
          Add Product
        </Button>
        <Button 
          variant="contained" 
          onClick={scrapeAll}
          disabled={loading}
        >
          {loading ? 'Scraping...' : 'Scrape All'}
        </Button>
      </Box>
    </Container>
  );
}

export default App;
