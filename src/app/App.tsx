import { useEffect, useState } from 'react';
import { MutationWorkbench } from '../features/mutations/MutationWorkbench';
import { ConvergenceWorkbench } from '../features/convergence/ConvergenceWorkbench';

export function App() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const update = () => setHash(window.location.hash);
    window.addEventListener('hashchange', update);
    return () => window.removeEventListener('hashchange', update);
  }, []);
  useEffect(() => {
    document.title = hash === '#convergence' ? 'Signal Foundry | Convergence Testing' : 'Signal Foundry | Mutation Studio';
  }, [hash]);
  return hash === '#convergence' ? <ConvergenceWorkbench /> : <MutationWorkbench />;
}
