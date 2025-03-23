import json
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

class QuicPerformanceAnalyzer:
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        plt.style.use('default')
    
    def load_results(self, filename):
        with open(self.output_dir / filename, 'r') as f:
            return json.load(f)
    
    def create_throughput_comparison(self, data):
        """Create visualizations comparing throughput across stream counts and packet sizes"""
        # Extract data for plotting
        plot_data = []
        
        for test_key, test_data in data.items():
            num_streams = test_data['number_of_streams']
            for result in test_data['message_size_results']:
                plot_data.append({
                    'Stream Count': num_streams,
                    'Packet Size': int(str(result['size'])),  # Handle both string and int
                    'Throughput (Mbps)': result['total_throughput_mbps'],
                    'Messages/sec': result['messages_per_second'],
                    'Duration (s)': result['duration']
                })
        
        df = pd.DataFrame(plot_data)
        
        # 1. Line plot: Throughput vs Packet Size for each stream count
        plt.figure(figsize=(12, 6))
        for streams in sorted(df['Stream Count'].unique()):
            subset = df[df['Stream Count'] == streams]
            plt.plot(subset['Packet Size'], subset['Throughput (Mbps)'], 
                    marker='o', label=f'{streams} Streams')
        
        plt.xscale('log', base=2)
        plt.xlabel('Packet Size (bytes)')
        plt.ylabel('Throughput (Mbps)')
        plt.title('Throughput vs Packet Size for Different Stream Counts')
        plt.legend()
        plt.grid(True)
        plt.savefig(self.output_dir / 'throughput_vs_size.png')
        plt.close()
        
        # 2. Heatmap: Stream Count vs Packet Size with throughput as color
        plt.figure(figsize=(10, 6))
        pivot_table = df.pivot(index='Stream Count', columns='Packet Size', values='Throughput (Mbps)')
        sns.heatmap(pivot_table, annot=True, fmt='.1f', cmap='YlOrRd')
        plt.title('Throughput (Mbps) Heatmap')
        plt.savefig(self.output_dir / 'throughput_heatmap.png')
        plt.close()
        
        return df

    def analyze_stream_fairness(self, data):
        """Analyze fairness between streams for multi-stream tests"""
        fairness_data = []
        
        for test_key, test_data in data.items():
            num_streams = test_data['number_of_streams']
            if num_streams > 1:  # Only analyze multi-stream tests
                for result in test_data['message_size_results']:
                    packet_size = int(str(result['size']))
                    streams = result['per_stream_results']
                    
                    # Get throughput for each stream
                    if isinstance(streams, list):
                        throughputs = [s.get('mbits_per_second', s.get('bytes_per_second', 0) * 8 / 1_000_000) 
                                    for s in streams]
                    else:
                        continue
                    
                    # Calculate fairness metrics
                    mean_throughput = np.mean(throughputs)
                    std_throughput = np.std(throughputs)
                    cv = std_throughput / mean_throughput if mean_throughput else 0
                    jains_fairness = (np.sum(throughputs) ** 2) / (len(throughputs) * np.sum(np.array(throughputs) ** 2)) if throughputs else 0
                    
                    fairness_data.append({
                        'Stream Count': num_streams,
                        'Packet Size': packet_size,
                        'Mean Throughput': mean_throughput,
                        'Std Dev': std_throughput,
                        'CV': cv,
                        'Jains Fairness': jains_fairness
                    })
        
        if fairness_data:
            df = pd.DataFrame(fairness_data)
            
            # Create fairness heatmap
            plt.figure(figsize=(10, 6))
            pivot_table = df.pivot(index='Stream Count', columns='Packet Size', values='Jains Fairness')
            sns.heatmap(pivot_table, annot=True, cmap='YlOrRd', vmin=0, vmax=1)
            plt.title("Jain's Fairness Index Across Stream Counts and Packet Sizes")
            plt.savefig(self.output_dir / 'fairness_heatmap.png')
            plt.close()
            
            # Create CV heatmap
            plt.figure(figsize=(10, 6))
            pivot_table = df.pivot(index='Stream Count', columns='Packet Size', values='CV')
            sns.heatmap(pivot_table, annot=True, cmap='YlOrRd_r')
            plt.title("Coefficient of Variation Across Stream Counts and Packet Sizes")
            plt.savefig(self.output_dir / 'cv_heatmap.png')
            plt.close()
            
            return df
        return pd.DataFrame()

    def create_performance_summary(self, data):
        """Create detailed performance summary with statistics"""
        summary_data = []
        
        for test_key, test_data in data.items():
            num_streams = test_data['number_of_streams']
            for result in test_data['message_size_results']:
                summary = {
                    'Stream Count': num_streams,
                    'Packet Size (bytes)': int(str(result['size'])),
                    'Total Throughput (Mbps)': result['total_throughput_mbps'],
                    'Messages/sec': result['messages_per_second'],
                    'Duration (s)': result['duration'],
                    'Total Messages': result['total_messages'],
                    'Total Bytes': result['total_bytes']
                }
                
                if num_streams > 1 and isinstance(result['per_stream_results'], list):
                    throughputs = [s.get('mbits_per_second', s.get('bytes_per_second', 0) * 8 / 1_000_000) 
                                for s in result['per_stream_results']]
                    summary.update({
                        'Min Stream Throughput': min(throughputs),
                        'Max Stream Throughput': max(throughputs),
                        'Mean Stream Throughput': np.mean(throughputs),
                        'Throughput Std Dev': np.std(throughputs)
                    })
                
                summary_data.append(summary)
        
        df = pd.DataFrame(summary_data)
        df.to_csv(self.output_dir / 'performance_summary.csv', index=False)
        return df

    def comprehensive_analysis(self, data):
        """Run comprehensive analysis on the performance data"""
        print("\nRunning comprehensive performance analysis...")
        
        # 1. Throughput analysis
        throughput_df = self.create_throughput_comparison(data)
        print("\nThroughput Analysis:")
        print("-" * 50)
        throughput_stats = throughput_df.groupby('Stream Count').agg({
            'Throughput (Mbps)': ['mean', 'max', 'std'],
            'Messages/sec': ['mean', 'max']
        }).round(2)
        print(throughput_stats.to_string())
        
        # 2. Fairness analysis for multi-stream tests
        fairness_df = self.analyze_stream_fairness(data)
        if not fairness_df.empty:
            print("\nFairness Analysis:")
            print("-" * 50)
            fairness_stats = fairness_df.groupby('Stream Count').agg({
                'Jains Fairness': ['mean', 'min'],
                'CV': ['mean', 'max']
            }).round(3)
            print(fairness_stats.to_string())
        
        # 3. Performance summary
        summary_df = self.create_performance_summary(data)
        print("\nPerformance Summary (Best Results per Stream Count):")
        print("-" * 50)
        best_results = summary_df.loc[summary_df.groupby('Stream Count')['Total Throughput (Mbps)'].idxmax()]
        print(best_results[['Stream Count', 'Packet Size (bytes)', 'Total Throughput (Mbps)', 'Messages/sec']].to_string(index=False))

def main():
    # Initialize analyzer
    base_dir = Path(__file__).parent
    analyzer = QuicPerformanceAnalyzer(base_dir / 'qlogs')
    
    # Load and analyze performance metrics
    print("Loading performance metrics from performance_metrics.json...")
    data = analyzer.load_results('performance_metrics.json')
    analyzer.comprehensive_analysis(data)
    
    print("\nAnalysis complete! Generated files in the 'qlogs' directory:")
    print("- throughput_vs_size.png: Line plot comparing throughput across stream counts")
    print("- throughput_heatmap.png: Heatmap showing throughput distribution")
    print("- fairness_heatmap.png: Heatmap of Jain's Fairness Index")
    print("- cv_heatmap.png: Heatmap of Coefficient of Variation")
    print("- performance_summary.csv: Detailed performance metrics")

if __name__ == "__main__":
    main()
