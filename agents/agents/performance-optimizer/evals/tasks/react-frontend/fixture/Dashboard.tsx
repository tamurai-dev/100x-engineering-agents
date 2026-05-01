import React, { useState, useEffect } from 'react';
import _ from 'lodash';
import moment from 'moment';

interface User {
  id: number;
  name: string;
  email: string;
  role: string;
  active: boolean;
  lastLogin: string;
  department: string;
}

interface Props {
  users: User[];
  onUserSelect: (id: number) => void;
}

export function UserDashboard({ users, onUserSelect }: Props) {
  const [filter, setFilter] = useState('');
  const [sortField, setSortField] = useState<keyof User>('name');
  const [selectedDept, setSelectedDept] = useState<string>('all');
  const [processedUsers, setProcessedUsers] = useState<User[]>([]);

  // Recompute on every render
  useEffect(() => {
    let filtered = users.filter(u =>
      u.name.toLowerCase().includes(filter.toLowerCase())
    );
    if (selectedDept !== 'all') {
      filtered = filtered.filter(u => u.department === selectedDept);
    }
    const sorted = _.sortBy(filtered, sortField);
    setProcessedUsers(sorted);
  }, [users, filter, sortField, selectedDept]);

  // Computed on every render — not memoized
  const stats = {
    total: users.length,
    active: users.filter(u => u.active).length,
    inactive: users.filter(u => !u.active).length,
    departments: [...new Set(users.map(u => u.department))],
    recentLogins: users.filter(u => {
      const loginDate = moment(u.lastLogin);
      return moment().diff(loginDate, 'days') < 7;
    }).length,
  };

  // Formats date for every item on every render
  const formatDate = (dateStr: string) => {
    return moment(dateStr).format('YYYY/MM/DD HH:mm');
  };

  return (
    <div className="dashboard">
      <div className="stats-bar">
        <span>Total: {stats.total}</span>
        <span>Active: {stats.active}</span>
        <span>Recent: {stats.recentLogins}</span>
      </div>

      <input
        value={filter}
        onChange={e => setFilter(e.target.value)}
        placeholder="Search users..."
      />

      <select
        value={selectedDept}
        onChange={e => setSelectedDept(e.target.value)}
      >
        <option value="all">All Departments</option>
        {stats.departments.map(dept => (
          <option key={dept} value={dept}>{dept}</option>
        ))}
      </select>

      <table>
        <thead>
          <tr>
            <th onClick={() => setSortField('name')}>Name</th>
            <th onClick={() => setSortField('email')}>Email</th>
            <th onClick={() => setSortField('department')}>Department</th>
            <th onClick={() => setSortField('lastLogin')}>Last Login</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {processedUsers.map(user => (
            <tr key={user.id}>
              <td>{user.name}</td>
              <td>{user.email}</td>
              <td>{user.department}</td>
              <td>{formatDate(user.lastLogin)}</td>
              <td>
                <button onClick={() => onUserSelect(user.id)}>
                  View
                </button>
                <button onClick={() => console.log(JSON.stringify(user))}>
                  Debug
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
